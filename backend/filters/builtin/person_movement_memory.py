"""Context filter: person_movement_memory (uses PersonLocationService fallback).

Gates rules on movement transitions. Primary path: semantic memory client.
Fallback: PersonLocationService.presence_history for installations without
semantic memory configured.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.filters import FilterRegistry
from backend.filters.base import ContextFilter, FilterMetadata


@FilterRegistry.register
class PersonMovementMemoryFilter(ContextFilter):
    """Rule context filter that checks for person movement transitions."""

    @classmethod
    def metadata(cls) -> FilterMetadata:
        return FilterMetadata(
            filter_type="person_movement_memory",
            display_name="Person Movement Memory",
            description=(
                "Checks whether a person has made a specific movement transition "
                "within a configurable time window."
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
                        "enum": [
                            "entering",
                            "exiting",
                            "approaching_exit",
                            "entering_depth",
                            "stationary",
                            "any",
                        ],
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
        db: Any = None,
        services: Any = None,
    ) -> bool:
        person_id: str = config.get("person_id", "")
        if not person_id:
            return False

        semantic: str | None = config.get("semantic", "any")
        if semantic == "any":
            semantic = None
        to_room_id: str | None = config.get("to_room_id") or None
        within_minutes: int = config.get("within_minutes", 30)
        min_confidence: float = config.get("min_confidence", 0.0)

        # Primary: semantic memory client.
        if services is not None and services.semantic_memory_client is not None:
            client = services.semantic_memory_client
            transitions = await client.get_transitions(
                person_id,
                semantic=semantic,
                to_room_id=to_room_id,
                since_minutes=within_minutes,
            )
            return any(t.confidence >= min_confidence for t in transitions)

        # PersonLocationService presence_history fallback.
        if services is not None and services.person_location is not None:
            try:
                cutoff = now - timedelta(minutes=within_minutes)
                segments = await services.person_location.presence_history(
                    person_id, since=cutoff, until=now
                )
            except Exception:  # noqa: BLE001
                return False

            active = [s for s in segments if s.superseded_by is None]
            if len(active) < 2:
                return False

            for i in range(1, len(active)):
                prev = active[i - 1]
                curr = active[i]
                if prev.room_id == curr.room_id:
                    continue
                if to_room_id and str(curr.room_id) != to_room_id:
                    continue
                if semantic:
                    if semantic == "entering" and curr.entry_source not in (
                        "observed",
                        "inferred_transit",
                    ):
                        continue
                    if semantic == "exiting" and prev.exit_source not in (
                        "observed",
                        "inferred_transit",
                        "contradicted",
                    ):
                        continue
                return True
            return False

        return False
