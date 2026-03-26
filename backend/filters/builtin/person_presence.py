"""Person presence context filter -- is person X in room Y?"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PersonPresenceFilter(ContextFilter):

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="person_presence",
            display_name="Person Presence",
            description="Check if a person is currently in a specific room or is tracked as home.",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "room_name": {
                        "type": "string",
                        "description": "Optional room to check (empty = just check person is home)",
                    },
                },
                "required": ["person_id"],
            },
        )

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        if not db:
            return False
        from backend.models.person import PersonLocationState

        person_id = config.get("person_id")
        room_name = config.get("room_name")
        if not person_id:
            return False

        loc = (
            db.query(PersonLocationState)
            .filter(PersonLocationState.person_id == person_id)
            .first()
        )
        if not loc:
            return False
        if room_name:
            return (loc.current_room_name or "").lower() == room_name.lower()
        return loc.status == "home"
