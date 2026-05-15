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

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
from backend.services.cts import metrics
from backend.services.cts._time import ns_to_iso
from backend.services.cts._types import ConnectionManager, MinioClient, PipelineExecutor
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

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

    # -- StreamConsumer abstract methods ------------------------------------

    def decode(self, message_id: bytes, fields: dict[bytes | str, bytes | str]) -> dict[str, Any] | None:
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

        # MAP identities live on IdentityRevision sub-messages; the top
        # candidate's probability acts as the per-detection confidence.
        identity_by_track: dict[str, tuple[str, float]] = {}
        for revision in message.identity_revisions:
            if not revision.global_track_id or not revision.map_identity_id:
                continue
            confidence = next(
                (
                    float(c.probability)
                    for c in revision.candidates
                    if c.identity_id == revision.map_identity_id
                ),
                0.0,
            )
            identity_by_track[revision.global_track_id] = (
                revision.map_identity_id,
                confidence,
            )

        detections: list[dict[str, Any]] = []
        for det in message.detections:
            identity_id, identity_conf = identity_by_track.get(
                det.global_track_id, ("", 0.0)
            )
            detections.append(
                {
                    "id": det.detection_id,
                    "tracklet_id": det.tracklet_id,
                    "global_track_id": det.global_track_id,
                    "identity_id": identity_id,
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


