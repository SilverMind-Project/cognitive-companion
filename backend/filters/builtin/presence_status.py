"""presence_status context filter: match on fused PresenceStatus.

Gates a rule when the person's location status matches the configured value.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PresenceStatusFilter(ContextFilter):
    """Gate on the person's current location / presence status."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="presence_status",
            display_name="Presence Status",
            description="Match when a person's presence status equals the configured value.",
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

    async def evaluate(
        self,
        config: dict,
        sensor: Any,
        now: datetime,
        db: Any = None,
        services: Any = None,
    ) -> bool:
        person_id = (config.get("person_id") or "").strip() or None
        status = config.get("status")
        if not person_id or not status:
            return False

        room_name = config.get("room_name")

        # Use PersonLocationService when available.
        if (
            services
            and hasattr(services, "person_location")
            and services.person_location is not None
        ):
            try:
                current = await services.person_location.where_is(person_id)
            except Exception:  # noqa: BLE001
                return False

            # Differentiate absence semantics explicitly.
            if status in ("away", "stale", "unknown"):
                return current is None
            if current is None:
                return False
            if status == "present_room" and room_name and current.room_name:
                return current.room_name.lower() == room_name.lower()
            # present_home, asleep: any presence is sufficient.
            return True

        # Legacy fallback: use presence service.
        if services and hasattr(services, "presence") and services.presence is not None:
            try:
                snapshot = await services.presence.get(person_id)
            except Exception:  # noqa: BLE001
                return False
            if snapshot.status.value != status:
                return False
            if room_name and snapshot.room_name:
                return snapshot.room_name.lower() == room_name.lower()
            return True

        return False
