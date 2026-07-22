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
    "ObservationDraft",
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
class ObservationDraft:
    """Caller-facing input to ``SceneIntelService.persist_observation``.

    Callers outside ``scene_intel`` build this instead of importing the
    integration client's ``ObservationCreate`` directly (DL8: the raw
    semantic-memory schema stays private to the service).
    """

    room_id: str | None = None
    description: str = ""
    object_list: list[str] = field(default_factory=list)
    hazard_flags: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    source: str = "scene_intel"
    # DL-M05: person attribution and record-kind taxonomy. ``kind`` defaults
    # to "scene" so existing writers (CTS scene samples, person movements)
    # keep writing legacy-shaped rows without callers touching this field.
    person_id: str | None = None
    kind: str = "scene"
    # 768-dim text embedding (embeddinggemma), kept separate from
    # ``embedding`` (CLIP image embedding) so text search over episode
    # summaries never mixes with image-similarity search.
    description_embedding: list[float] = field(default_factory=list)


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
