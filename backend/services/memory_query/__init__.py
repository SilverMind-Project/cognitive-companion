"""MemoryQueryService -- read-side counterpart for semantic memory.

Consolidates the two public read patterns currently scattered across
``semantic_memory_query.py`` and ``object_trend_analysis.py``:

- ``room_context()`` -- observations + objects + hazards for a room.
- ``room_trends()`` -- object trends + snapshots for a room.
- ``search()`` -- free-text vector search.
"""

from __future__ import annotations

from backend.services.memory_query.service import MemoryQueryService
from backend.services.memory_query.types import (
    HazardObservation,
    ObjectPresenceRecord,
    ObservationSearchHit,
    RoomContext,
    RoomTrendContext,
    RoomTrendResult,
    TrendSnapshot,
)

__all__ = [
    "HazardObservation",
    "MemoryQueryService",
    "ObjectPresenceRecord",
    "ObservationSearchHit",
    "RoomContext",
    "RoomTrendContext",
    "RoomTrendResult",
    "TrendSnapshot",
]
