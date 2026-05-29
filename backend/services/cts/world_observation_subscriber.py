"""Subscribes to tracking.events for world-tracker observations (M4).

Decodes TrackingEvent protos and feeds them to
PersonLocationService.ingest_observation with source='world_tracker'.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint

STREAM = "tracking.events"
GROUP = "cognitive-companion-m4-world-obs"


class WorldObservationSubscriber(StreamConsumer[dict]):
    def __init__(
        self,
        redis_url: str,
        location_service: PersonLocationService,
        camera_room_map: dict[str, str] | None = None,
        config: ConsumerConfig | None = None,
    ) -> None:
        super().__init__(
            config or ConsumerConfig(
                redis_url=redis_url,
                stream=STREAM,
                group=GROUP,
                consumer_id="m4-world-obs",
            )
        )
        self._location = location_service
        self._camera_room_map = camera_room_map or {}

    async def decode(self, message_id: str, fields: dict) -> dict | None:
        """Decode a tracking event proto and extract world-observation data."""
        if b"event" not in fields:
            return None
        try:
            from backend.integrations.proto.continuoustracking.v1 import (
                tracking_pb2,
            )

            proto = tracking_pb2.TrackingEvent.FromString(fields[b"event"])
        except Exception:
            return None

        event_time = datetime.fromtimestamp(
            proto.event_time_unix_ns / 1e9, tz=UTC
        )
        result: dict = {
            "event_time": event_time,
            "room_name": proto.room_name,
            "camera_id": proto.camera_id,
            "detections": [],
        }
        for det in proto.detections:
            identity_id = None
            for snap in proto.identity_snapshots:
                if snap.ph_id == det.global_track_id:  # R3: snap uses ph_id; det uses deprecated alias
                    identity_id = snap.identity_id or None
                    break
            result["detections"].append({
                "camera_id": proto.camera_id,
                "detection_id": det.detection_id,
                "ph_id": det.global_track_id,
                "identity_id": identity_id,
                "confidence": det.confidence,
                "floor_x_mm": det.floor_point.x_mm if det.floor_point else 0,
                "floor_y_mm": det.floor_point.y_mm if det.floor_point else 0,
                "room_name": proto.room_name,
                "calibrated": det.floor_point.calibrated if det.floor_point else False,
            })
        return result

    async def handle(self, msg: dict) -> bool:
        for det in msg.get("detections", []):
            if not det.get("identity_id"):
                continue
            if not det.get("calibrated"):
                continue
            floor_x = det["floor_x_mm"] / 1000.0
            floor_y = det["floor_y_mm"] / 1000.0

            # Resolve room_id: prefer camera→room mapping over raw room_name.
            room_name = det.get("room_name", "") or msg.get("room_name", "")
            room_id = self._resolve_room_id(det.get("camera_id", ""), room_name)

            await self._location.ingest_observation(
                person_id=str(det["identity_id"]),
                observed_at=msg["event_time"],
                source="world_tracker",
                source_ref=det.get("ph_id"),
                floor_point=FloorPoint(x_m=floor_x, y_m=floor_y),
                room_id=room_id,
                confidence=det.get("confidence", 0.5),
                metadata={
                    "camera_id": det.get("camera_id", ""),
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
            except (ValueError, TypeError):
                pass
        return None
