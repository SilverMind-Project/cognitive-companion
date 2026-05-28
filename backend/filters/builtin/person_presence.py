"""Person presence context filter -- is person X home / away / in room Y? (R2: PersonLocationService SSOT)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.core.logging import get_logger
from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata
from backend.services.cts.metrics import cts_filter_degraded_total

logger = get_logger(__name__)

_FILTER_NAME = "person_presence"


@FilterRegistry.register
class PersonPresenceFilter(ContextFilter):
    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="person_presence",
            display_name="Person Presence",
            description="Check if a person is home, away, or in a specific room.",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["home", "away", "unknown"],
                        "description": "Required presence status (default: home)",
                    },
                    "room_name": {
                        "type": "string",
                        "description": "Optional room to check (only meaningful when status is home)",
                    },
                },
                "required": ["person_id"],
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
        person_id = (config.get("person_id") or "").strip() or None
        if not person_id:
            return False

        status = config.get("status", "home")
        room_name = config.get("room_name")

        # R2: PersonLocationService is the SSOT.  Fail closed when unavailable.
        if not (services and getattr(services, "person_location", None)):
            cts_filter_degraded_total.labels(filter=_FILTER_NAME).inc()
            logger.warning(
                "cts_filter_degraded_no_person_location",
                filter=_FILTER_NAME,
            )
            return False

        current = await services.person_location.where_is(person_id)

        if status == "away":
            return current is None
        if status == "unknown":
            return False
        # status == "home"
        if current is None:
            return False
        if room_name:
            return (current.room_name or "").lower() == room_name.lower()
        return True
