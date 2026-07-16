"""Room context filter: match rule to specific rooms using PersonLocationService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.core.logging import get_logger
from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata
from backend.services.cts.metrics import cts_filter_degraded_total

logger = get_logger(__name__)

_FILTER_NAME = "room"


@FilterRegistry.register
class RoomFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="room",
            display_name="Room",
            description="Filter rules by room name or ID. Uses PersonLocationService (SSOT).",
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
        db: Any = None,
        services: Any = None,
    ) -> bool:
        room_id = config.get("room_id")
        room_name = config.get("room_name", "")

        person_id = config.get("person_id", "")
        if not person_id:
            return False

        # PersonLocationService is the SSOT.  Fail closed when unavailable.
        if services is None or services.person_location is None:
            cts_filter_degraded_total.labels(filter=_FILTER_NAME).inc()
            logger.warning(
                "cts_filter_degraded_no_person_location",
                filter=_FILTER_NAME,
            )
            return False

        current = await services.person_location.where_is(str(person_id))
        if current is None:
            return False

        if room_id:
            return str(current.room_id) == str(room_id)
        if room_name:
            return (current.room_name or "").lower() == room_name.lower()
        return True
