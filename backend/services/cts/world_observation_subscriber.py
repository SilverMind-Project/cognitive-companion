"""Subscribes to tracking.events for world-tracker observations (M4).

Decodes WorldTrackerObservationEvent protos and feeds them to
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
        config: ConsumerConfig | None = None,
    ) -> None:
        super().__init__(
            redis_url=redis_url,
            stream=STREAM,
            group=GROUP,
            config=config or ConsumerConfig(consumer_id="m4-world-obs"),
        )
        self._location = location_service

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
            "detections": [],
        }
        for det in proto.detections:
            identity_id = None
            for snap in proto.identity_snapshots:
                if snap.global_track_id == det.global_track_id:
                    identity_id = snap.identity_id or None
                    break
            result["detections"].append({
                "camera_id": proto.camera_id,
                "detection_id": det.detection_id,
                "ph_id": det.global_track_id,  # N0: proto field 1 reused for ph_id
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
            await self._location.ingest_observation(
                person_id=str(det["identity_id"]),
                observed_at=msg["event_time"],
                source="world_tracker",
                source_ref=det.get("ph_id"),
                floor_point=FloorPoint(x_m=floor_x, y=floor_y),
                confidence=det.get("confidence", 0.5),
                metadata={
                    "camera_id": det.get("camera_id", ""),
                    "room_name": det.get("room_name", ""),
                },
            )
        return True
