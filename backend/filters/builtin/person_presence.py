"""Person presence context filter -- is person X home / away / in room Y?"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

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
                    "within_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 15,
                        "description": "Staleness window in minutes for last-seen heuristic.",
                    },
                    "use_semantic_memory": {
                        "type": "boolean",
                        "default": False,
                        "description": "Use semantic memory movements to corroborate presence.",
                    },
                },
                "required": ["person_id"],
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
        if not db:
            return False
        from backend.models.person import PersonLocationState

        person_id = config.get("person_id")
        if not person_id:
            return False

        status = config.get("status", "home")
        room_name = config.get("room_name")
        within_minutes: int = config.get("within_minutes", 15)
        use_semantic_memory: bool = config.get("use_semantic_memory", False)

        loc = (
            db.query(PersonLocationState).filter(PersonLocationState.person_id == person_id).first()
        )

        # -- Semantic memory path ----------------------------------------------
        if use_semantic_memory and services and getattr(services, "semantic_memory_client", None):
            client = services.semantic_memory_client
            transitions = asyncio.get_event_loop().run_until_complete(
                client.get_transitions(
                    person_id,
                    since_minutes=within_minutes,
                )
            )
            if transitions:
                latest = max(transitions, key=lambda t: t.observed_at)
                if room_name:
                    return (latest.to_room_id or "").lower() == room_name.lower()
                return True
            # No transitions found — fall through to local heuristic
            return False

        is_home = self._is_home(loc, now, within_minutes)

        if status == "away":
            return not is_home
        if status == "unknown":
            return loc is None or loc.status == "unknown"

        # status == "home" (default)
        if not is_home or loc is None:
            return False
        if room_name:
            return (loc.current_room_name or "").lower() == room_name.lower()
        return True

    @staticmethod
    def _is_home(loc, now: datetime, stale_minutes: int = 15) -> bool:
        if not loc or loc.status != "home":
            return False
        if loc.last_seen_at:
            stale_cutoff = now - timedelta(minutes=stale_minutes)
            if loc.last_seen_at < stale_cutoff:
                return False
        return True
