"""home_state context filter -- match on high-level home/away/asleep state.

Gates a rule when the person's fused presence status maps to the configured
high-level home state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class HomeStateFilter(ContextFilter):
    """Gate on the person's high-level home state."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="home_state",
            display_name="Home State",
            description="Match when a person's home state is at home, asleep, away, or unknown.",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person to evaluate.",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["at_home", "asleep", "away", "unknown"],
                        "description": "Required home state.",
                    },
                },
                "required": ["state"],
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

        state = config.get("state")
        if not state:
            return False

        # Use PersonLocationService (async-safe).
        if services is not None and services.person_location is not None:
            try:
                current = await services.person_location.where_is(person_id)
            except Exception:  # noqa: BLE001
                return False
            if current is None:
                return state in ("away", "unknown")
            if state == "at_home":
                return True
            if state == "asleep":
                return getattr(current, "is_inferred", False)
            if state == "away":
                return False
            if state == "unknown":
                return False
            return False

        # Legacy fallback: presence service.
        if services is not None and services.presence is not None:
            try:
                snapshot = await services.presence.get(person_id)
            except Exception:  # noqa: BLE001
                return False
            status = snapshot.status.value
            if state == "at_home":
                return status in ("present_room", "present_home", "asleep")
            if state == "asleep":
                return status == "asleep"
            if state == "away":
                return status == "away"
            if state == "unknown":
                return status in ("unknown", "stale")
            return False

        return False
