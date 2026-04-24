"""TrackingEventSubscriber: consume tracking.events and apply to location state.

Decodes :mod:`backend.services.cts.stream_consumer`-shaped messages from the
``tracking.events`` Redis Stream, reassembles the flat field payload into a
structured event dict, and delegates to :class:`LocationWriter`.

The wire format is currently JSON-flat (see tech-debt TD-001/TD-004). The
decoder is tolerant of missing per-detection fields: events published by
older orchestrator builds simply produce ``identity_id=""`` detections that
:class:`LocationWriter` skips cleanly.
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer

logger = get_logger(__name__)


class TrackingEventSubscriber(StreamConsumer[dict[str, Any]]):
    """Consume ``tracking.events`` and apply them to PersonLocationState.

    Parameters
    ----------
    redis_url:
        Redis connection URL.
    consumer_id:
        Unique ID for this consumer instance (usually ``socket.gethostname()``).
    writer:
        :class:`LocationWriter` that persists the event to CC tables.
    ws_manager:
        Optional :class:`ConnectionManager` for live bbox broadcasts.
    pipeline:
        Optional pipeline executor; fires ``cts.event`` events when a rule
        wants to key off raw tracking events.
    """

    STREAM = "tracking.events"
    GROUP = "cognitive-companion-events"

    def __init__(
        self,
        redis_url: str,
        consumer_id: str,
        writer: LocationWriter,
        ws_manager: Any = None,
        pipeline: Any = None,
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

    # -- StreamConsumer abstract methods ------------------------------------

    def decode(self, message_id: bytes, fields: dict) -> dict[str, Any] | None:
        """Reassemble the flat field payload into an event dict.

        The orchestrator serializes one Redis Stream field per detection
        attribute (e.g. ``detection.0.bbox_xmin``).  We re-group them here
        so downstream code sees a structured dict.
        """
        decoded = {_k(k): _v(v) for k, v in fields.items()}

        event: dict[str, Any] = {
            "event_id": decoded.get("event_id", ""),
            "camera_id": decoded.get("camera_id", ""),
            "event_time": _event_time_iso(decoded.get("event_time_unix_ns", "0")),
            "frame_index": _to_int(decoded.get("frame_index")),
            "detection_count": _to_int(decoded.get("detection_count")),
            "minio_key": decoded.get("minio_key", ""),
            "room_name": decoded.get("room_name", "") or None,
        }

        detections: list[dict[str, Any]] = []
        indexes = _detection_indexes(decoded)
        for idx in sorted(indexes):
            detections.append(
                {
                    "id": decoded.get(f"detection.{idx}.id", ""),
                    "tracklet_id": decoded.get(f"detection.{idx}.tracklet_id", ""),
                    "global_track_id": decoded.get(f"detection.{idx}.global_track_id", ""),
                    "identity_id": decoded.get(f"detection.{idx}.identity_id", ""),
                    "identity_confidence": _to_float(
                        decoded.get(f"detection.{idx}.identity_confidence")
                    ),
                    "confidence": _to_float(decoded.get(f"detection.{idx}.confidence")),
                    "bbox": {
                        "x_min": _to_int(decoded.get(f"detection.{idx}.bbox_xmin")),
                        "y_min": _to_int(decoded.get(f"detection.{idx}.bbox_ymin")),
                        "x_max": _to_int(decoded.get(f"detection.{idx}.bbox_xmax")),
                        "y_max": _to_int(decoded.get(f"detection.{idx}.bbox_ymax")),
                    },
                    "floor_point": {
                        "x_mm": _to_int(decoded.get(f"detection.{idx}.floor_x_mm")),
                        "y_mm": _to_int(decoded.get(f"detection.{idx}.floor_y_mm")),
                    },
                }
            )
        event["detections"] = detections

        return event

    async def handle(self, event: dict[str, Any]) -> bool:
        """Apply the event to CC location state."""
        try:
            touched = await self._writer.apply(event)
        except Exception:
            logger.exception("tracking_event_apply_error", camera=event.get("camera_id"))
            return False

        if self._ws_manager is not None and event.get("detections"):
            # Broadcast the raw frame payload for the Live view.
            try:
                await self._ws_manager.broadcast(
                    {
                        "type": "cts_live_frame",
                        "camera_id": event["camera_id"],
                        "event_time": event["event_time"],
                        "room_name": event.get("room_name"),
                        "minio_key": event.get("minio_key"),
                        "detections": event["detections"],
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

        return True


# ---------------------------------------------------------------------------
# Helpers (decode a Redis-Streams flat bytes dict into a clean Python dict)
# ---------------------------------------------------------------------------


def _k(key: Any) -> str:
    return key.decode("utf-8") if isinstance(key, bytes | bytearray) else str(key)


def _v(value: Any) -> str:
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _event_time_iso(ns_str: str) -> str:
    """Convert unix-ns string to ISO-8601 UTC."""
    from datetime import UTC, datetime

    try:
        ns = int(ns_str)
    except (TypeError, ValueError):
        ns = 0
    if ns <= 0:
        return datetime.now(UTC).isoformat()
    return datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()


def _detection_indexes(decoded: dict[str, str]) -> set[int]:
    """Find unique detection indexes referenced by the flat fields."""
    idxs: set[int] = set()
    for key in decoded:
        if not key.startswith("detection."):
            continue
        parts = key.split(".")
        if len(parts) >= 2:
            try:
                idxs.add(int(parts[1]))
            except ValueError:
                continue
    return idxs
