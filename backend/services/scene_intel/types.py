"""Domain types for SceneIntelService."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from backend.integrations.scene_analysis_client import (
    SceneAnalyzeResult,
    SceneDetection,
    SceneHazardAlert,
)

# ---------------------------------------------------------------------------
# Re-exports (public API surface for callers)
# ---------------------------------------------------------------------------

__all__ = [
    "RoomTransition",
    "SceneAnalyzeResult",
    "SceneDetection",
    "SceneHazardAlert",
    "SceneIntelRecord",
    "SceneRunFlags",
]


class SceneRunFlags(StrEnum):
    """Which sub-models to run during scene analysis."""

    DETECT = "detect"
    DESCRIBE = "describe"
    EMBED = "embed"
    HAZARDS = "hazards"

    @property
    def run_detect(self) -> bool:
        return self in (self.DETECT,)

    @property
    def run_describe(self) -> bool:
        return self in (self.DESCRIBE,)

    @property
    def run_embed(self) -> bool:
        return self in (self.EMBED,)

    @property
    def run_hazards(self) -> bool:
        return self in (self.HAZARDS,)


@dataclass(frozen=True)
class RoomTransition:
    """A single room-to-room movement derived from camera topology."""

    person_id: str
    from_room_id: str
    to_room_id: str
    direction_semantic: str = "any"
    confidence: float = 0.8
    observed_at: datetime | None = None


@dataclass(frozen=True)
class SceneIntelRecord:
    """Return type for ``persist`` / ``analyze_and_persist``."""

    observation_id: int | None = None
    movement_ids: list[int] = field(default_factory=list)
    source: str = "scene_intel"

    @classmethod
    def empty(cls) -> SceneIntelRecord:
        return cls(observation_id=None, movement_ids=[])
