"""home_state context filter -- match on high-level home/away/asleep state.

Gates a rule when the person's fused presence status maps to the configured
high-level home state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

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

    def evaluate(
        self,
        config: dict,
        sensor: Any,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool:
        if not services or services.presence is None:
            return False

        person_id = (config.get("person_id") or "").strip() or None
        if not person_id:
            return False

        state = config.get("state")
        if not state:
            return False

        try:
            import asyncio

            snapshot = asyncio.run(services.presence.get(person_id))
        except Exception:
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
