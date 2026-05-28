"""Subscribes to tracking.room_transitions for transit zone events (M4).

Decodes RoomTransitionEvent payloads and feeds them to
PersonLocationService.ingest_room_transition.

WTR4: PersonLocationService is injected, not constructed per message.
"""

from __future__ import annotations

from datetime import datetime

from backend.core.logging import get_logger
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer
from backend.services.person_location.service import PersonLocationService

logger = get_logger(__name__)

STREAM = "tracking.room_transitions"
GROUP = "cognitive-companion-m4-room-trans"


class RoomTransitionSubscriber(StreamConsumer[dict]):
    def __init__(
        self,
        redis_url: str,
        location_service: PersonLocationService,
        config: ConsumerConfig | None = None,
    ) -> None:
        super().__init__(
            config or ConsumerConfig(
                redis_url=redis_url,
                stream=STREAM,
                group=GROUP,
                consumer_id="m4-room-trans",
            )
        )
        self._location = location_service

    async def decode(self, message_id: str, fields: dict) -> dict | None:
        """Decode a room transition event from the Redis stream."""
        try:
            identity_id_raw = fields.get(b"identity_id", b"")
            identity_id = identity_id_raw.decode() if identity_id_raw else None
            return {
                "ph_id": fields.get(b"ph_id", b"").decode(),
                "identity_id": identity_id,
                "transit_zone_id": fields.get(b"transit_zone_id", b"").decode(),
                "direction": fields.get(b"direction", b"").decode(),
                "inside_room_id": fields.get(b"inside_room_id", b"").decode(),
                "outside_room_id": fields.get(b"outside_room_id", b"").decode(),
                "floor_x_m": float(fields.get(b"floor_x_m", b"0").decode()),
                "floor_y_m": float(fields.get(b"floor_y_m", b"0").decode()),
                "event_time": datetime.fromisoformat(
                    fields.get(b"event_time", b"").decode()
                ),
            }
        except Exception:
            return None

    async def handle(self, msg: dict) -> bool:
        identity_id = msg.get("identity_id")
        if not identity_id:
            logger.debug(
                "room_transition_skipped_no_identity",
                ph_id=msg.get("ph_id"),
            )
            return True

        await self._location.ingest_room_transition(
            person_id=str(identity_id),
            transit_zone_id=str(msg["transit_zone_id"]),
            direction=str(msg["direction"]),
            inside_room_id=int(msg["inside_room_id"]),
            outside_room_id=int(msg["outside_room_id"]),
            floor_x_m=float(msg["floor_x_m"]),
            floor_y_m=float(msg["floor_y_m"]),
            event_time=msg["event_time"],
        )
        return True
