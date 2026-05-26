"""Subscribes to tracking.room_transitions for transit zone events (M4).

Decodes RoomTransitionEvent payloads and feeds them to
PersonLocationService.ingest_room_transition.
"""

from __future__ import annotations

from datetime import datetime

from backend.services.cts._types import DBSessionFactory
from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer
from backend.services.person_location.repositories import (
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService

STREAM = "tracking.room_transitions"
GROUP = "cognitive-companion-m4-room-trans"


class RoomTransitionSubscriber(StreamConsumer[dict]):
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
            config=config or ConsumerConfig(consumer_id="m4-room-trans"),
        )
        self._db_factory = db_factory

    async def decode(self, message_id: str, fields: dict) -> dict | None:
        """Decode a room transition event from the Redis stream."""
        try:
            return {
                "ph_id": fields.get(b"ph_id", b"").decode(),
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
        db = self._db_factory()
        try:
            svc = PersonLocationService(
                obs_repo=SqlAlchemyObservationRepository(db),
                seg_repo=SqlAlchemySegmentRepository(db),
            )
            await svc.ingest_room_transition(
                person_id=str(msg["ph_id"]),
                transit_zone_id=msg["transit_zone_id"],
                direction=msg["direction"],
                inside_room_id=int(msg["inside_room_id"]),
                outside_room_id=int(msg["outside_room_id"]),
                floor_x_m=msg["floor_x_m"],
                floor_y_m=msg["floor_y_m"],
                event_time=msg["event_time"],
            )
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
