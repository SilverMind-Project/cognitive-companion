"""TrackingEventSubscriber: consume tracking.events and apply to location state.

Decodes :class:`TrackingEvent` proto messages from the ``tracking.events``
Redis Stream, translates them into the dict shape that :class:`LocationWriter`
consumes, and forwards live-frame broadcasts to the WebSocket fan-out.

Wire format
-----------
Each Redis Streams message carries one field, ``event``, whose value is the
raw protobuf body of a ``continuoustracking.v1.TrackingEvent``. The
orchestrator publishes via ``RedisStreamsTransport.publish_event``; this
subscriber is the only consumer.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
from backend.schemas.cts_ph_ws import PHUpdateEvent
from backend.services.cts import metrics
from backend.services.cts._time import ns_to_iso
from backend.services.cts._types import ConnectionManager, MinioClient, PipelineExecutor
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer
from backend.services.cts.world_snapshot_publisher import WorldSnapshotPublisher

# TrackingEvents whose capture_time_unix_ns is older than this are replayed
# backlog.  Returning None from decode() causes the base class to XACK and
# skip handle(), keeping the live view free of historical frames.
_MAX_TRACKING_EVENT_AGE_S: float = 30.0

logger = get_logger(__name__)

# Redis Streams field name carrying the proto body.
FIELD = b"event"

# Live frames are displayed within seconds of capture; keep the window tight.
_LIVE_FRAME_TTL = 30


class TrackingEventSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.events`` and apply them to PersonLocationState."""

    STREAM = "tracking.events"
    GROUP = "cognitive-companion-events"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        writer: LocationWriter,
        ws_manager: ConnectionManager | None = None,
        pipeline: PipelineExecutor | None = None,
        bucketizer: Any = None,
        minio_client: MinioClient | None = None,
        snapshot_publisher: WorldSnapshotPublisher | None = None,
    ) -> None:
        super().__init__(
            ConsumerConfig(
                redis_url=redis_url,
                stream=self.STREAM,
                group=self.GROUP,
                consumer_id=consumer_id,
                concurrency=2,
            )
        )
        self._writer = writer
        self._ws_manager = ws_manager
        self._pipeline = pipeline
        self._bucketizer = bucketizer
        self._minio_client = minio_client
        self._snapshot_publisher = snapshot_publisher
        self._ph_pending: dict[str, asyncio.Task[None]] = {}

    # -- StreamConsumer abstract methods ------------------------------------

    def decode(
        self, message_id: bytes, fields: dict[bytes | str, bytes | str]
    ) -> dict[str, Any] | None:
        """Decode the proto envelope into the LocationWriter event dict."""
        payload = fields.get(FIELD) or fields.get(FIELD.decode())
        if payload is None:
            logger.warning("tracking_event_missing_payload", message_id=message_id)
            return None
        if isinstance(payload, str):
            payload = payload.encode("latin-1")

        try:
            message = tracking_pb2.TrackingEvent.FromString(payload)
        except Exception:
            logger.exception("tracking_event_proto_decode_error", message_id=message_id)
            metrics.cts_events_decode_errors.inc()
            return None

        capture_ns = message.frame_ref.capture_time_unix_ns
        if capture_ns > 0:
            age_s = datetime.now(UTC).timestamp() - capture_ns / 1e9
            if age_s > _MAX_TRACKING_EVENT_AGE_S:
                logger.warning(
                    "stale_tracking_event_dropped",
                    camera_id=message.camera_id,
                    age_s=round(age_s, 1),
                )
                metrics.cts_events_stale_dropped.inc()
                return None

        # WTR3: build identity map from identity_snapshots (field 8),
        # not the deprecated identity_revisions (field 5).
        identity_by_ph: dict[str, tuple[str, float, str]] = {}
        for snap in message.identity_snapshots:
            # WTR3: global_track_id carries the PH id.
            ph_id = snap.global_track_id
            if not ph_id:
                continue
            identity_by_ph[ph_id] = (
                snap.identity_id,
                snap.top_probability,
                snap.identity_id,  # display_name
            )

        # Fallback: read from deprecated identity_revisions for old orchestrators.
        if not identity_by_ph:
            for revision in message.identity_revisions:
                track_key = revision.ph_id
                if not track_key or not revision.map_identity_id:
                    continue
                matched = next(
                    (c for c in revision.candidates if c.identity_id == revision.map_identity_id),
                    None,
                )
                confidence = float(matched.probability) if matched else 0.0
                display_name = (
                    matched.display_name
                    if (matched and matched.display_name)
                    else revision.map_identity_id
                )
                identity_by_ph[track_key] = (
                    revision.map_identity_id,
                    confidence,
                    display_name,
                )

        detections: list[dict[str, Any]] = []
        for det in message.detections:
            # WTR3: global_track_id carries the PH id in the proto.
            ph_id = det.global_track_id
            identity_id, identity_conf, display_name = identity_by_ph.get(
                ph_id, ("", 0.0, "")
            )
            calibrated = det.floor_point.calibrated
            detections.append(
                {
                    "id": det.detection_id,
                    "ph_id": ph_id,
                    "tracklet_id": det.tracklet_id,
                    "identity_id": identity_id or None,
                    "display_name": display_name or None,
                    "identity_confidence": identity_conf,
                    "confidence": det.confidence,
                    "bbox": {
                        "x_min": det.bbox.x_min,
                        "y_min": det.bbox.y_min,
                        "x_max": det.bbox.x_max,
                        "y_max": det.bbox.y_max,
                    },
                    "floor_point": {
                        "x_mm": det.floor_point.x_mm,
                        "y_mm": det.floor_point.y_mm,
                    },
                    "floor_calibrated": calibrated,
                    "floor_x": det.floor_x if calibrated else None,
                    "floor_y": det.floor_y if calibrated else None,
                    "pose_keypoints": [
                        {"x": kp.x, "y": kp.y, "score": kp.score} for kp in det.pose_keypoints
                    ]
                    or None,
                    "posture": det.posture or None,
                    "trail": [{"x": t.x, "y": t.y} for t in det.trail] or None,
                    "evidence": {
                        "top_prob": det.evidence.top_prob,
                        "top2_prob": det.evidence.top2_prob,
                        "face_anchor_used": det.evidence.face_anchor_used,
                    }
                    if det.HasField("evidence")
                    else None,
                }
            )

        # N2: extract identity snapshots for PH update broadcasts
        identity_snapshots: list[dict[str, Any]] = []
        for snap in message.identity_snapshots:
            if snap.identity_id:
                identity_snapshots.append(
                    {
                        "ph_id": snap.global_track_id,
                        "identity_id": snap.identity_id,
                        "top_probability": snap.top_probability,
                        "second_probability": snap.second_probability,
                        "posterior_entropy": snap.posterior_entropy,
                        "direct_face_evidence": snap.direct_face_evidence,
                    }
                )

        return {
            "event_id": message.event_id,
            "camera_id": message.camera_id,
            "event_time": ns_to_iso(message.event_time_unix_ns),
            "frame_index": int(message.frame_ref.frame_index),
            "detection_count": len(detections),
            "minio_key": message.frame_ref.minio_key,
            "room_name": message.room_name or None,
            "frame_width": int(message.frame_ref.width),
            "frame_height": int(message.frame_ref.height),
            "capture_time": ns_to_iso(message.frame_ref.capture_time_unix_ns),
            "detections": detections,
            "identity_snapshots": identity_snapshots,
        }

    async def handle(self, event: dict[str, Any]) -> bool:
        """Apply the event to CC location state."""
        camera_id = event.get("camera_id", "unknown")
        metrics.cts_events_received.labels(event_type=camera_id).inc()

        try:
            touched = await self._writer.apply(event)
        except Exception:
            logger.exception("tracking_event_apply_error", camera=event.get("camera_id"))
            metrics.cts_events_dropped.labels(event_type=camera_id).inc()
            return False

        metrics.cts_events_persisted.labels(event_type=camera_id).inc()

        if self._ws_manager is not None:
            try:
                frame_url: str | None = None
                minio_key = event.get("minio_key")
                if minio_key:
                    if self._minio_client is not None:
                        frame_url = self._minio_client.generate_presigned_url(
                            minio_key, expiration=_LIVE_FRAME_TTL
                        )
                        logger.info(
                            "cts_live_frame_url_generated",
                            camera_id=camera_id,
                            has_frame_url=bool(frame_url),
                            frame_url_preview=frame_url[:80] if frame_url else None,
                        )
                    else:
                        logger.warning(
                            "cts_live_no_minio_client",
                            camera_id=camera_id,
                            minio_key=minio_key,
                        )
                else:
                    logger.info("cts_live_no_minio_key", camera_id=camera_id)
                await self._ws_manager.broadcast(
                    {
                        "type": "cts_live_frame",
                        "camera_id": event["camera_id"],
                        "event_time": event["event_time"],
                        "room_name": event.get("room_name"),
                        "minio_key": event.get("minio_key"),
                        "frame_url": frame_url,
                        "frame_width": event.get("frame_width", 0),
                        "frame_height": event.get("frame_height", 0),
                        "capture_time": event.get("capture_time"),
                        "detections": event.get("detections", []),
                    }
                )
            except Exception:
                logger.exception("cts_live_broadcast_error")

            # N2: broadcast PH updates from identity snapshots
            # Per-PH 200 ms debounce to avoid flooding the WebSocket bus.
            try:
                for snap in event.get("identity_snapshots", []):
                    ph_id = snap.get("ph_id", "")
                    if not ph_id:
                        continue
                    evt = PHUpdateEvent(
                        ph_id=ph_id,
                        current_identity_id=snap.get("identity_id") or None,
                        identity_committed=bool(snap.get("identity_id")),
                        state="active",
                        posterior_top_label=snap.get("identity_id") or None,
                        posterior_top_prob=float(snap.get("top_probability", 0.0)),
                        last_observed_at=event.get("capture_time"),
                    )
                    payload = evt.model_dump(mode="json")

                    existing = self._ph_pending.get(ph_id)
                    if existing is not None and not existing.done():
                        existing.cancel()

                    async def _emit(p: dict = payload, pid: str = ph_id) -> None:
                        await asyncio.sleep(0.2)
                        if self._ws_manager is not None:
                            await self._ws_manager.broadcast(p)

                    task = asyncio.create_task(_emit())
                    task.add_done_callback(
                        lambda t, pid=ph_id: self._ph_pending.pop(pid, None)
                    )
                    self._ph_pending[ph_id] = task
            except Exception:
                logger.exception("cts_ph_update_broadcast_error")

            # N4: delegate world snapshot to debounced publisher
            if self._snapshot_publisher is not None:
                phs = self._build_ph_entries(event)
                if phs:
                    self._snapshot_publisher.mark_dirty(ph_data_list=phs)

        if self._pipeline is not None and touched:
            try:
                await self._pipeline.fire_event(
                    source="cts",
                    kind="tracking_event",
                    payload={
                        "camera_id": event["camera_id"],
                        "event_time": event["event_time"],
                        "persons": touched,
                        "room_name": event.get("room_name"),
                    },
                )
            except Exception:
                logger.exception("tracking_event_pipeline_fire_error")

        if self._bucketizer is not None:
            try:
                self._bucketizer.ingest(event)
            except Exception:
                logger.exception("tracking_event_bucketizer_ingest_error")

        return True

    def _build_ph_entries(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Build PH position entries from tracking event detections (WTR3)."""
        identity_map: dict[str, dict[str, Any]] = {}
        for snap in event.get("identity_snapshots", []):
            identity_map[snap.get("ph_id", "")] = {
                "identity_id": snap.get("identity_id"),
                "display_name": snap.get("identity_id"),
                "color": "#888888",
                "top_prob": snap.get("top_probability", 0.0),
            }
        phs: list[dict[str, Any]] = []
        for det in event.get("detections", []):
            # R3: ph_id is the canonical PH identifier.
            ph_id = det.get("ph_id", "")
            identity = identity_map.get(ph_id, {})
            calibrated = det.get("floor_calibrated", False)
            phs.append(
                {
                    "ph_id": ph_id,
                    "identity_id": identity.get("identity_id"),
                    "identity_display_name": identity.get("display_name"),
                    "identity_color": identity.get("color", "#888888"),
                    "identity_committed": bool(identity.get("identity_id")),
                    "posterior_top_label": identity.get("identity_id"),
                    "posterior_top_prob": identity.get("top_prob", 0.0),
                    "room_id": None,
                    "room_name": event.get("room_name") or "",
                    "room_has_camera": True,
                    "floor_xy_m": [
                        det.get("floor_x") or 0.0,
                        det.get("floor_y") or 0.0,
                    ],
                    "velocity_mps": [0.0, 0.0],
                    "posture": det.get("posture") or "unknown",
                    "state": "active",
                    "last_observed_at": event.get("capture_time"),
                    "uncalibrated": not calibrated,
                    "presence_source": "observed" if calibrated else "unknown",
                }
            )
        return phs

    async def stop(self) -> None:
        """Cancel pending debounce tasks, then delegate to base class."""
        for task in list(self._ph_pending.values()):
            if not task.done():
                task.cancel()
        self._ph_pending.clear()
        await super().stop()
