"""Context filter: scene_contains.

Gates rules on "object or hazard has been observed in this room within
the last N minutes" using the object-presence and observation search
endpoints of the semantic-memory-service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class SceneContainsFilter(ContextFilter):
    """Rule context filter that checks for objects or hazards in recent scene memory."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="scene_contains",
            display_name="Scene Contains",
            description=(
                "Checks whether a specific object or hazard has been observed "
                "in a room within a configurable time window, using semantic memory."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "Room ID to check.",
                    },
                    "objects_any": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "Object labels to look for (any match passes).",
                    },
                    "hazard_flags_any": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": "Hazard flags to look for (any match passes).",
                    },
                    "within_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 30,
                        "description": "Lookback window in minutes.",
                    },
                    "min_observation_count": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 1,
                        "description": "Minimum observation count for an object to match.",
                    },
                },
                "required": ["room_id"],
            },
        )

    async def evaluate(
        self,
        config: dict,
        sensor: Any,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool:
        if not services or not services.semantic_memory_client:
            return False

        client = services.semantic_memory_client
        room_id: str = config.get("room_id", "")
        if not room_id:
            return False

        within_minutes: int = config.get("within_minutes", 30)
        objects_any: list[str] = config.get("objects_any", [])
        hazard_flags_any: list[str] = config.get("hazard_flags_any", [])
        min_count: int = config.get("min_observation_count", 1)

        # At least one criterion must be non-empty
        if not objects_any and not hazard_flags_any:
            return False

        passed = False

        # Objects path
        if objects_any:
            recent = await client.get_recent_objects(room_id, since_minutes=within_minutes)
            for rec in recent:
                if rec.label in objects_any and rec.observation_count >= min_count:
                    passed = True
                    break

        # Hazards path (OR semantics)
        if not passed and hazard_flags_any:
            from backend.integrations.semantic_memory_client import ObservationSearchRequest

            req = ObservationSearchRequest(
                room_id=room_id,
                since_minutes=within_minutes,
                hazard_flags_any=hazard_flags_any,
            )
            hits = await client.search_observations(req)
            if hits:
                passed = True

        return passed
