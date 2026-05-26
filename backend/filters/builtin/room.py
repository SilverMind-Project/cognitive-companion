"""Room context filter -- match rule to specific rooms (M4: uses PersonLocationService)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

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
            description="Filter rules by room name or ID. Uses unified location service (M4).",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "room_id": {"type": "string"},
                    "room_name": {"type": "string"},
                },
            },
        )

    async def evaluate(
        self,
        config: dict,
        sensor: Any,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool:
        room_id = config.get("room_id")
        room_name = config.get("room_name", "")

        # M4: use PersonLocationService when available.
        person_id = config.get("person_id", "")
        if person_id and services and hasattr(services, "person_location"):
            current = await services.person_location.where_is(UUID(person_id))
            if current is None:
                return False
            if room_id:
                return str(current.room_id) == str(room_id)
            return False

        # Legacy fallback: check sensor properties.
        if room_id and hasattr(sensor, "room_id") and sensor.room_id:
            return str(sensor.room_id) == str(room_id)
        if room_name and hasattr(sensor, "room"):
            return sensor.room.name.lower() == room_name.lower()
        return False
