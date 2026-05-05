"""Domain types for MemoryQueryService.

Re-exports the existing client schemas so step handlers never need
to import ``SemanticMemoryClient`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.integrations.semantic_memory_client import (
    ObjectPresenceRecord,
    ObservationSearchHit,
    RoomTrendResult,
    TrendSnapshot,
)

# ---------------------------------------------------------------------------
# Re-exports (public API surface for callers)
# ---------------------------------------------------------------------------

__all__ = [
    "HazardObservation",
    "ObjectPresenceRecord",
    "ObservationSearchHit",
    "RoomContext",
    "RoomTrendContext",
    "RoomTrendResult",
    "TrendSnapshot",
]


@dataclass(frozen=True)
class HazardObservation:
    """A single observation that carried a hazard flag."""

    id: int
    room_id: str
    observed_at: datetime
    hazard_flags: list[str]
    description: str


@dataclass(frozen=True)
class RoomContext:
    """Aggregated memory context for a single room.

    Mirrors the dict shape that ``semantic_memory_query`` step writes
    into ``pipeline_data`` under ``output_key``.
    """

    room_id: str
    recent_objects: tuple[ObjectPresenceRecord, ...] = field(default_factory=tuple)
    recent_hazards: tuple[HazardObservation, ...] = field(default_factory=tuple)
    observations: tuple[ObservationSearchHit, ...] = field(default_factory=tuple)
    summary: str = ""
    observations_count: int = 0


@dataclass(frozen=True)
class RoomTrendContext:
    """Aggregated trend data for a single room.

    Mirrors the dict shape that ``object_trend_analysis`` step writes
    into ``pipeline_data`` under ``output_key``.
    """

    room_id: str
    clutter_score: float = 0.0
    trend_direction: str = ""
    overall_severity: str = "ok"
    persistent_objects: list[str] = field(default_factory=list)
    novel_objects: list[str] = field(default_factory=list)
    anomalies: tuple[dict, ...] = field(default_factory=tuple)
    snapshots: tuple[TrendSnapshot, ...] | None = None
