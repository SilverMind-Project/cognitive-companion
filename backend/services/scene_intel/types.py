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
    "person_count_from_frames",
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
    # When the scene was captured. ``None`` means the caller has no capture
    # time and the write time is an acceptable approximation.
    observed_at: datetime | None = None
    # How many people were present. ``None`` means "not counted" and must stay
    # distinguishable from 0 ("counted, room empty"). Never a sum across frames:
    # see ``person_count_from_frames``.
    persons_count: int | None = None
    # Object names of the frames this observation was assembled from, so a
    # reader can get back to the imagery. One observation may span many frames
    # and, in a multi-camera room, many cameras.
    media_paths: list[str] = field(default_factory=list)
    # Full detection dicts (label, confidence, bbox) behind ``object_list``.
    objects: list[dict] = field(default_factory=list)


def person_count_from_frames(
    frames: list[dict],
    *,
    label: str = "person",
    min_confidence: float = 0.0,
    detections_field: str = "scene_detections",
) -> tuple[int | None, list[int]]:
    """Return ``(max_per_frame, per_frame_counts)`` for *frames*.

    Counting people across a multi-frame window is not a sum. One person
    standing in front of a camera for five frames yields five ``person``
    detections, and adding them reports five people. Deduplicating properly
    needs re-identification across frames, which this path does not have, so
    the honest aggregate is the maximum seen in any single frame: a floor,
    read as "at least this many people were present".

    The per-frame vector is returned alongside so callers can show the spread
    rather than a single collapsed integer.

    Returns ``(None, [])`` when *frames* carries no usable detection lists, so
    "not counted" stays distinct from "counted zero".
    """
    counts: list[int] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        detections = frame.get(detections_field)
        if not isinstance(detections, list):
            continue
        counts.append(
            sum(
                1
                for d in detections
                if isinstance(d, dict)
                and d.get("label") == label
                and float(d.get("confidence") or 0.0) >= min_confidence
            )
        )
    if not counts:
        return None, []
    return max(counts), counts


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
