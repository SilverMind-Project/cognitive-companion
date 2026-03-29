"""Person presence context filter -- is person X home / away / in room Y?"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

    # Locations older than this are considered stale / away.
    _STALE_MINUTES = 30

    def evaluate(self, config: dict, sensor, now: datetime, db: Session | None = None) -> bool:
        if not db:
            return False
        from backend.models.person import PersonLocationState

        person_id = config.get("person_id")
        if not person_id:
            return False

        status = config.get("status", "home")
        room_name = config.get("room_name")

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

        # status == "home" (default)
        if not is_home:
            return False
        if room_name:
            return (loc.current_room_name or "").lower() == room_name.lower()
        return True

    @staticmethod
    def _is_home(loc, now: datetime) -> bool:
        if not loc or loc.status != "home":
            return False
        if loc.last_seen_at:
            stale_cutoff = now - timedelta(minutes=PersonPresenceFilter._STALE_MINUTES)
            # Compare as offset-aware if possible
            last_seen = loc.last_seen_at
            if last_seen.tzinfo is None and now.tzinfo is not None:
                last_seen = last_seen.replace(tzinfo=UTC)
            if last_seen < stale_cutoff:
                return False
        return True
