"""Subscribes to tracking.events for world-tracker observations.

Decodes TrackingEvent protos and feeds them to
PersonLocationService.ingest_observation with source='world_tracker'.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from backend.core.logging import get_logger
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer, StreamFields
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint

logger = get_logger(__name__)

STREAM = "tracking.events"
GROUP = "cognitive-companion-m4-world-obs"
FIELD = b"event"


class WorldObservationDetection(TypedDict):
    camera_id: str
    detection_id: str
    ph_id: str
    identity_id: str | None
    confidence: float
    mean_quality: float
    floor_x_mm: int
    floor_y_mm: int
    room_name: str
    calibrated: bool


class WorldObservationMessage(TypedDict):
    event_time: datetime
    room_name: str
    camera_id: str
    detections: list[WorldObservationDetection]


class WorldObservationSubscriber(StreamConsumer[WorldObservationMessage]):
    def __init__(
        self,
        redis_url: str,
        location_service: PersonLocationService,
        camera_room_map: dict[str, str] | None = None,
        config: ConsumerConfig | None = None,
    ) -> None:
        super().__init__(
            config
            or ConsumerConfig(
                redis_url=redis_url,
                stream=STREAM,
                group=GROUP,
                consumer_id="m4-world-obs",
            )
        )
        self._location = location_service
        self._camera_room_map = camera_room_map or {}

    def decode(self, message_id: bytes, fields: StreamFields) -> WorldObservationMessage | None:
        """Decode a tracking event proto and extract world-observation data."""
        payload = _get_bytes_field(fields, FIELD)
        if payload is None:
            logger.warning("world_observation_missing_payload", message_id=message_id)
            return None
        try:
            from backend.integrations.proto.continuoustracking.v1 import (
                tracking_pb2,
            )

            proto = tracking_pb2.TrackingEvent.FromString(payload)
        except Exception:  # noqa: BLE001
            logger.warning(
                "world_observation_proto_decode_error",
                message_id=message_id,
                exc_info=True,
            )
            return None

        event_time = datetime.fromtimestamp(proto.event_time_unix_ns / 1e9, tz=UTC)
        result: WorldObservationMessage = {
            "event_time": event_time,
            "room_name": proto.room_name,
            "camera_id": proto.camera_id,
            "detections": [],
        }
        for det in proto.detections:
            identity_id = None
            mean_quality = 0.0
            for snap in proto.identity_snapshots:
                if snap.ph_id == det.ph_id:
                    identity_id = snap.identity_id or None
                    mean_quality = float(snap.mean_quality)  # PH quality from CTS wire
                    break
            result["detections"].append(
                {
                    "camera_id": proto.camera_id,
                    "detection_id": det.detection_id,
                    "ph_id": det.ph_id,
                    "identity_id": identity_id,
                    "confidence": det.confidence,
                    "mean_quality": mean_quality,
                    "floor_x_mm": det.floor_point.x_mm if det.floor_point else 0,
                    "floor_y_mm": det.floor_point.y_mm if det.floor_point else 0,
                    "room_name": proto.room_name,
                    "calibrated": det.floor_point.calibrated if det.floor_point else False,
                }
            )
        return result

    async def handle(self, msg: WorldObservationMessage) -> bool:
        for det in msg["detections"]:
            if not det["identity_id"]:
                continue
            if not det["calibrated"]:
                continue
            floor_x = det["floor_x_mm"] / 1000.0
            floor_y = det["floor_y_mm"] / 1000.0

            # Resolve room_id: prefer camera→room mapping over raw room_name.
            room_name = det["room_name"] or msg["room_name"]
            room_id = self._resolve_room_id(det["camera_id"], room_name)

            await self._location.ingest_observation(
                person_id=det["identity_id"],
                observed_at=msg["event_time"],
                source="world_tracker",
                source_ref=det["ph_id"],
                floor_point=FloorPoint(x_m=floor_x, y_m=floor_y),
                room_id=room_id,
                confidence=det["confidence"],
                quality=det["mean_quality"],
                metadata={
                    "camera_id": det["camera_id"],
                    "room_name": room_name,
                },
            )
        return True

    def _resolve_room_id(self, camera_id: str, room_name: str) -> int | None:
        """Resolve room_id from camera→room map or return None.

        Returns None when no room identity can be determined; callers
        should not persist empty room names as room identity.
        """
        mapped = self._camera_room_map.get(camera_id)
        if mapped:
            try:
                return int(mapped)
            except (TypeError, ValueError):
                pass
        return None


def _get_bytes_field(fields: StreamFields, key: bytes) -> bytes | None:
    raw = fields.get(key)
    if raw is None:
        raw = fields.get(key.decode())
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return raw
