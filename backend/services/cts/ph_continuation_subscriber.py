"""Subscribes to tracking.continuations for PH continuation candidates (M4).

Stitches presumed-presence links across PH closures for camera-blind rooms.
"""

from __future__ import annotations

from uuid import UUID

from backend.services.cts._types import DBSessionFactory
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer
from backend.services.person_location.repositories import (
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService

STREAM = "tracking.continuations"
GROUP = "cognitive-companion-m4-ph-cont"


class PHContinuationSubscriber(StreamConsumer[dict]):
    def __init__(
        self,
        redis_url: str,
        db_factory: DBSessionFactory,
        config: ConsumerConfig | None = None,
    ) -> None:
        super().__init__(
            redis_url=redis_url,
            stream=STREAM,
            group=GROUP,
            config=config or ConsumerConfig(consumer_id="m4-ph-cont"),
        )
        self._db_factory = db_factory

    async def decode(self, message_id: str, fields: dict) -> dict | None:
        """Decode a PH continuation candidate from the Redis stream."""
        try:
            return {
                "predecessor_ph_id": fields.get(b"predecessor_ph_id", b"").decode(),
                "successor_ph_id": fields.get(b"successor_ph_id", b"").decode(),
                "predecessor_identity_id": fields.get(b"predecessor_identity_id", b"").decode() or None,
            }
        except Exception:
            return None

    async def handle(self, msg: dict) -> bool:
        """Stitch continuation: if the predecessor had an inferred segment,
        carry it forward to the successor PH."""
        db = self._db_factory()
        try:
            svc = PersonLocationService(
                obs_repo=SqlAlchemyObservationRepository(db),
                seg_repo=SqlAlchemySegmentRepository(db),
            )
            pred_id = msg.get("predecessor_identity_id")
            succ_id = msg.get("successor_ph_id")
            if pred_id and succ_id:
                # Check if predecessor has an open inferred segment.
                dwell = await svc.current_dwell(UUID(pred_id))
                if dwell is not None and dwell.is_inferred:
                    # Carry forward: open an inferred segment for the successor
                    # at the same room with the same entered_at time.
                    from datetime import UTC, datetime

                    await svc.ingest_room_transition(
                        person_id=UUID(succ_id),
                        transit_zone_id="ph_continuation",
                        direction="enter",
                        inside_room_id=dwell.room_id,
                        outside_room_id=dwell.room_id,
                        floor_x_m=0.0,
                        floor_y_m=0.0,
                        event_time=datetime.now(UTC),
                    )
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
