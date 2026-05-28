"""Subscribes to tracking.continuations for PH continuation candidates (M4).

Stitches presumed-presence links across PH closures for camera-blind rooms.

WTR4: Uses predecessor_identity_id as person_id, successor_ph_id as source_ref.
Does not coerce person_id to UUID.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.core.logging import get_logger
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer
from backend.services.person_location.service import PersonLocationService

logger = get_logger(__name__)

STREAM = "tracking.continuations"
GROUP = "cognitive-companion-m4-ph-cont"


class PHContinuationSubscriber(StreamConsumer[dict]):
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
                consumer_id="m4-ph-cont",
            )
        )
        self._location = location_service

    async def decode(self, message_id: str, fields: dict) -> dict | None:
        """Decode a PH continuation candidate from the Redis stream."""
        try:
            return {
                "predecessor_ph_id": fields.get(b"predecessor_ph_id", b"").decode(),
                "successor_ph_id": fields.get(b"successor_ph_id", b"").decode(),
                "predecessor_identity_id": (
                    fields.get(b"predecessor_identity_id", b"").decode() or None
                ),
            }
        except Exception:
            return None

    async def handle(self, msg: dict) -> bool:
        """Stitch continuation: if the predecessor had an inferred segment,
        carry it forward to the successor PH using the predecessor's identity.

        WTR4: predecessor_identity_id is the person_id (string, not UUID).
        successor_ph_id is source_ref — it must not become the person_id.
        """
        pred_identity_id = msg.get("predecessor_identity_id")
        succ_ph_id = msg.get("successor_ph_id")
        if not pred_identity_id or not succ_ph_id:
            return True

        dwell = await self._location.current_dwell(str(pred_identity_id))
        if dwell is not None and dwell.is_inferred:
            await self._location.ingest_room_transition(
                person_id=str(pred_identity_id),
                transit_zone_id="ph_continuation",
                direction="enter",
                inside_room_id=dwell.room_id,
                outside_room_id=dwell.room_id,
                floor_x_m=0.0,
                floor_y_m=0.0,
                event_time=datetime.now(UTC),
            )
        return True
