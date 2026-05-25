"""presence_dwell context filter -- match on dwell duration.

Gates a rule when the person's fused presence dwell time in the current
room meets or exceeds the configured minimum.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PresenceDwellFilter(ContextFilter):
    """Gate on the person's presence dwell duration."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="presence_dwell",
            display_name="Presence Dwell",
            description="Match when a person has held the matching presence status for at least N minutes.",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person to evaluate.",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["present_room", "asleep"],
                        "default": "",
                        "description": ("Optional status filter. Empty = any status."),
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

        min_minutes = config.get("min_minutes")
        if min_minutes is None:
            return False

        status_filter = config.get("status", "")

        try:
            import asyncio

            snapshot = asyncio.run(services.presence.get(person_id))
        except Exception:
            return False

        if status_filter and snapshot.status.value != status_filter:
            return False

        dwell = snapshot.dwell_minutes
        if dwell is None:
            return False

        return dwell >= min_minutes
