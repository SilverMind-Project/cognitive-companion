"""Subscribes to tracking.room_transitions for transit zone events.

Decodes RoomTransitionEvent payloads and feeds them to
PersonLocationService.ingest_room_transition.

PersonLocationService is injected, not constructed per message.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from backend.core.logging import get_logger
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer, StreamFields
from backend.services.person_location.service import PersonLocationService

logger = get_logger(__name__)

STREAM = "tracking.room_transitions"
GROUP = "cognitive-companion-m4-room-trans"


class RoomTransitionMessage(TypedDict):
    ph_id: str
    identity_id: str | None
    transit_zone_id: str
    direction: str
    inside_room_id: int
    outside_room_id: int
    event_time: datetime


class RoomTransitionSubscriber(StreamConsumer[RoomTransitionMessage]):
    def __init__(
        self,
        redis_url: str,
        location_service: PersonLocationService,
        config: ConsumerConfig | None = None,
    ) -> None:
        super().__init__(
            config
            or ConsumerConfig(
                redis_url=redis_url,
                stream=STREAM,
                group=GROUP,
                consumer_id="m4-room-trans",
            )
        )
        self._location = location_service

    def decode(self, message_id: bytes, fields: StreamFields) -> RoomTransitionMessage | None:
        """Decode a room transition event from the Redis stream."""
        try:
            identity_id = _get_text_field(fields, b"identity_id") or None
            return {
                "ph_id": _get_text_field(fields, b"ph_id"),
                "identity_id": identity_id,
                "transit_zone_id": _get_text_field(fields, b"transit_zone_id"),
                "direction": _get_text_field(fields, b"direction"),
                "inside_room_id": int(_get_text_field(fields, b"inside_room_id")),
                "outside_room_id": int(_get_text_field(fields, b"outside_room_id")),
                "event_time": datetime.fromisoformat(_get_text_field(fields, b"event_time")),
            }
        except Exception:  # noqa: BLE001
            logger.warning(
                "room_transition_decode_error",
                message_id=message_id,
                exc_info=True,
            )
            return None

    async def handle(self, msg: RoomTransitionMessage) -> bool:
        identity_id = msg["identity_id"]
        if not identity_id:
            logger.debug(
                "room_transition_skipped_no_identity",
                ph_id=msg["ph_id"],
            )
            return True

        await self._location.ingest_room_transition(
            person_id=identity_id,
            transit_zone_id=msg["transit_zone_id"],
            direction=msg["direction"],
            inside_room_id=msg["inside_room_id"],
            outside_room_id=msg["outside_room_id"],
            event_time=msg["event_time"],
        )
        return True


def _get_text_field(fields: StreamFields, key: bytes) -> str:
    raw = fields.get(key)
    if raw is None:
        raw = fields.get(key.decode())
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode()
    return raw
