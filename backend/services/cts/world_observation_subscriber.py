"""Subscribes to tracking.events for world-tracker observations.

Decodes TrackingEvent protos and feeds them to
PersonLocationService.ingest_observation with source='world_tracker'.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.services.cts.member_provisioning import ensure_household_members
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer, StreamFields
from backend.services.occupancy.read_model import WORLD_TRACKER_SOURCE, OccupancyReadModel
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
        camera_room_id_map: dict[str, int] | None = None,
        camera_room_name_map: dict[str, str] | None = None,
        occupancy: OccupancyReadModel | None = None,
        db_factory: Callable[[], Session] | None = None,
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
        self._camera_room_id_map = camera_room_id_map or {}
        self._camera_room_name_map = camera_room_name_map or {}
        self._occupancy = occupancy
        self._db_factory = db_factory

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
        # Auto-provision a HouseholdMember for every identified detection so
        # the segment/observation FK to household_members is satisfied.
        identity_ids = {d["identity_id"] for d in msg["detections"] if d["identity_id"]}
        if identity_ids and self._db_factory is not None:
            ensure_household_members(self._db_factory, identity_ids)

        for det in msg["detections"]:
            room_id = self._camera_room_id_map.get(det["camera_id"])
            if room_id is None:
                # Logged skip, not silent: a camera with no assigned room
                # cannot contribute room presence (likely a config gap).
                logger.warning(
                    "world_observation_unmapped_camera",
                    camera_id=det["camera_id"],
                    ph_id=det["ph_id"],
                )
                continue

            room_name = (
                det["room_name"]
                or msg["room_name"]
                or self._camera_room_name_map.get(det["camera_id"], "")
            )

            # Occupancy is recorded for EVERY hypothesis, identified or not,
            # and is independent of calibration.
            if self._occupancy is not None:
                self._occupancy.record_room_presence(
                    room_id=room_id,
                    room_name=room_name,
                    ph_id=det["ph_id"],
                    identity_id=det["identity_id"] or None,
                    source=WORLD_TRACKER_SOURCE,
                    observed_at=msg["event_time"],
                )

            # A presence segment is only written for an identified person.
            if not det["identity_id"]:
                continue

            # Floor coordinates only when truly calibrated; synthetic tile
            # points must not masquerade as real floor positions. Room
            # membership comes from the camera map regardless.
            floor_point = None
            if det["calibrated"]:
                floor_point = FloorPoint(
                    x_m=det["floor_x_mm"] / 1000.0,
                    y_m=det["floor_y_mm"] / 1000.0,
                )

            await self._location.ingest_observation(
                person_id=det["identity_id"],
                observed_at=msg["event_time"],
                source="world_tracker",
                source_ref=det["ph_id"],
                floor_point=floor_point,
                room_id=room_id,
                confidence=det["confidence"],
                quality=det["mean_quality"],
                metadata={
                    "camera_id": det["camera_id"],
                    "room_name": room_name,
                },
            )
        return True


def _get_bytes_field(fields: StreamFields, key: bytes) -> bytes | None:
    raw = fields.get(key)
    if raw is None:
        raw = fields.get(key.decode())
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return raw
