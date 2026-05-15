"""Context filter: person_movement_memory.

Gates rules on movement transitions stored in semantic memory,
independent of local PersonLocationHistory.  All reads go through
SemanticMemoryClient.get_transitions — this filter never queries CTS
tables directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PersonMovementMemoryFilter(ContextFilter):
    """Rule context filter that checks semantic memory for person movement transitions."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="person_movement_memory",
            display_name="Person Movement Memory",
            description=(
                "Checks whether a person has made a specific movement transition "
                "within a configurable time window, using semantic memory."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "Person ID to check.",
                    },
                    "semantic": {
                        "type": "string",
                        "enum": ["entering", "exiting", "approaching_exit", "entering_depth", "stationary", "any"],
                        "default": "any",
                        "description": "Semantic direction to match.",
                    },
                    "to_room_id": {
                        "type": "string",
                        "description": "Optional target room ID to filter on.",
                    },
                    "within_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "default": 30,
                        "description": "Lookback window in minutes.",
                    },
                    "min_confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.0,
                        "description": "Minimum confidence threshold.",
                    },
                },
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
        person_id: str = config.get("person_id", "")
        if not person_id:
            return False

        semantic: str | None = config.get("semantic", "any")
        if semantic == "any":
            semantic = None
        to_room_id: str | None = config.get("to_room_id") or None
        within_minutes: int = config.get("within_minutes", 30)
        min_confidence: float = config.get("min_confidence", 0.0)

        transitions = await client.get_transitions(
            person_id,
            semantic=semantic,
            to_room_id=to_room_id,
            since_minutes=within_minutes,
        )

        return any(t.confidence >= min_confidence for t in transitions)
