"""presence_dwell context filter -- match on dwell duration (M4: uses PersonLocationService).

Gates a rule when the person has been in their current room for at least
the configured minimum minutes.  The dwell timer starts at segment entry
(entered_at), not at last observation (last_seen_at).  This means brief
occlusions do not reset the timer — the caregiver gets "she has been in
the bathroom for X minutes", not "we last saw her X minutes ago."
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PresenceDwellFilter(ContextFilter):
    """Gate on the person's presence dwell duration (entered_at-based)."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="presence_dwell",
            display_name="Presence Dwell",
            description=(
                "Match when a person has been in their current room for at least "
                "N minutes. Dwell is measured from the moment they entered the room, "
                "so brief occlusions or gaps in observation do not reset the timer."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person to evaluate.",
                    },
                    "min_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 5,
                        "description": "Minimum dwell time in minutes.",
                    },
                },
                "required": ["min_minutes"],
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

        min_minutes = config.get("min_minutes")
        if min_minutes is None:
            return False

        # M4: prefer PersonLocationService (entered_at-based dwell).
        if services and hasattr(services, "person_location") and services.person_location is not None:
            try:
                dwell = await services.person_location.current_dwell(person_id)
            except Exception:
                return False
            if dwell is None:
                return False
            # WTR7: use the injected ``now`` for deterministic tests.
            elapsed = (now - dwell.entered_at).total_seconds()
            return elapsed >= (min_minutes * 60)

        # Legacy fallback: use the presence service (last_seen_at-based).
        if services and hasattr(services, "presence") and services.presence is not None:
            try:
                snapshot = await services.presence.get(person_id)
            except Exception:
                return False
            dwell_mins = snapshot.dwell_minutes
            if dwell_mins is None:
                return False
            return dwell_mins >= min_minutes

        return False
