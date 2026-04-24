"""Room context filter -- match rule to specific rooms."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class RoomFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="room",
            display_name="Room",
            description="Filter rules by room name or ID.",
            config_schema={
                "type": "object",
                "properties": {
                    "room_name": {"type": "string"},
                    "room_id": {"type": "integer"},
                },
            },
        )

    def evaluate(
        self,
        config: dict,
        sensor,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool:
        room_name = config.get("room_name", "")
        room_id = config.get("room_id")
        if room_id and sensor.room_id:
            return sensor.room_id == room_id
        if room_name and sensor.room:
            return sensor.room.name.lower() == room_name.lower()
        return False
