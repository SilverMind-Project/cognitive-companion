"""Person presence context filter -- is person X home / away / in room Y? (M4: uses PersonLocationService)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


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

        # M4: use PersonLocationService when available.
        if services and hasattr(services, "person_location") and services.person_location is not None:
            try:
                current = await services.person_location.where_is(person_id)
            except Exception:
                return False

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

        # Legacy fallback: direct DB query.
        if db is not None:
            from backend.models.person import PersonLocationState

            loc = (
                db.query(PersonLocationState)
                .filter(PersonLocationState.person_id == person_id)
                .first()
            )
            is_home = self._is_home(loc, now)
            if status == "away":
                return not is_home
            if status == "unknown":
                return loc is None or loc.status == "unknown"
            if not is_home or loc is None:
                return False
            if room_name:
                return (loc.current_room_name or "").lower() == room_name.lower()
            return True

        return False

    @staticmethod
    def _is_home(loc, now: datetime) -> bool:
        return not (not loc or loc.status != "home")
