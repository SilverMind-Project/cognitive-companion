"""SceneIntelService -- write-side wrapper around scene-analysis + semantic-memory.

Consolidates the pattern in ``scene_analysis.py`` (analyze -> optionally
write observation) into one method, plus adds movement persistence.
Removes the pipeline-step author's need to know about ``ObservationCreate``
and ``MovementCreate`` schemas.
"""

from __future__ import annotations

from backend.services.scene_intel.service import SceneIntelService
from backend.services.scene_intel.types import (
    RoomTransition,
    SceneAnalyzeResult,
    SceneDetection,
    SceneHazardAlert,
    SceneIntelRecord,
    SceneRunFlags,
)

__all__ = [
    "RoomTransition",
    "SceneAnalyzeResult",
    "SceneDetection",
    "SceneHazardAlert",
    "SceneIntelRecord",
    "SceneIntelService",
    "SceneRunFlags",
]
