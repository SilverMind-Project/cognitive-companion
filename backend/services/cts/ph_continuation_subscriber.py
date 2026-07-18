"""Subscribes to tracking.continuations for PH continuation candidates.

Stitches presumed-presence links across PH closures for camera-blind rooms.

Uses predecessor_identity_id as person_id, successor_ph_id as source_ref.
Does not coerce person_id to UUID.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from backend.core.logging import get_logger
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer, StreamFields
from backend.services.person_location.service import PersonLocationService

logger = get_logger(__name__)

STREAM = "tracking.continuations"
GROUP = "cognitive-companion-m4-ph-cont"


class PHContinuationMessage(TypedDict):
    predecessor_ph_id: str
    successor_ph_id: str
    predecessor_identity_id: str | None


class PHContinuationSubscriber(StreamConsumer[PHContinuationMessage]):
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
                consumer_id="m4-ph-cont",
            )
        )
        self._location = location_service

    def decode(self, message_id: bytes, fields: StreamFields) -> PHContinuationMessage | None:
        """Decode a PH continuation candidate from the Redis stream."""
        try:
            return {
                "predecessor_ph_id": _get_text_field(fields, b"predecessor_ph_id"),
                "successor_ph_id": _get_text_field(fields, b"successor_ph_id"),
                "predecessor_identity_id": _get_text_field(fields, b"predecessor_identity_id")
                or None,
            }
        except Exception:  # noqa: BLE001
            logger.warning(
                "ph_continuation_decode_error",
                message_id=message_id,
                exc_info=True,
            )
            return None

    async def handle(self, msg: PHContinuationMessage) -> bool:
        """Stitch continuation: if the predecessor had an inferred segment,
        carry it forward to the successor PH using the predecessor's identity.

        predecessor_identity_id is the person_id (string, not UUID).
        successor_ph_id is source_ref — it must not become the person_id.
        """
        pred_identity_id = msg["predecessor_identity_id"]
        succ_ph_id = msg["successor_ph_id"]
        if not pred_identity_id or not succ_ph_id:
            return True

        dwell = await self._location.current_dwell(pred_identity_id)
        if dwell is not None and dwell.is_inferred:
            await self._location.ingest_room_transition(
                person_id=pred_identity_id,
                transit_zone_id="ph_continuation",
                direction="enter",
                inside_room_id=dwell.room_id,
                outside_room_id=dwell.room_id,
                event_time=datetime.now(UTC),
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
