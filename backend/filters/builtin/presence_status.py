"""presence_status context filter -- match on fused PresenceStatus.

Gates a rule when the person's fused presence status matches (or does not
match, when ``negate`` is True) the configured value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PresenceStatusFilter(ContextFilter):
    """Gate on the person's fused presence status."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="presence_status",
            display_name="Presence Status",
            description="Match when a person's fused presence status equals the configured value.",
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person to evaluate.",
                    },
                    "status": {
                        "type": "string",
                        "enum": [
                            "present_room",
                            "present_home",
                            "asleep",
                            "stale",
                            "away",
                            "unknown",
                        ],
                        "description": "Required presence status.",
                    },
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Optional room filter -- only meaningful when status is 'present_room'."
                        ),
                    },
                },
                "required": ["status"],
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

        status = config.get("status")
        if not status:
            return False

        room_name = config.get("room_name")

        try:
            import asyncio

            snapshot = asyncio.run(services.presence.get(person_id))
        except Exception:
            return False

        if snapshot.status.value != status:
            return False

        if room_name and snapshot.room_name:
            return snapshot.room_name.lower() == room_name.lower()

        return True
