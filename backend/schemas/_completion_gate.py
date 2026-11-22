"""Single-source completion_gate structure normalization.

Imported by both backend.schemas.guided_task (Pydantic input validation)
and backend.services.guided_task.routine_admin (service persistence) so
the allowed confirm/watch keys never drift between layers.
"""

from __future__ import annotations

import copy
from typing import Any

from backend.core.logging import get_logger

logger = get_logger(__name__)

_CONFIRM_KEYS: tuple[str, ...] = (
    "window_s",
    "max_frames",
    "max_cameras",
    "min_confidence",
    "min_interval_s",
    "model_id",
    "max_disagreements",
    "on_max_disagreements",
)

_WATCH_KEYS: tuple[str, ...] = (
    "enabled",
    "tick_s",
    "window_s",
    "max_frames",
    "max_cameras",
    "min_confidence",
    "model_id",
    "auto_advance",
    "auto_advance_k",
)


def normalize_completion_gate(gate: Any) -> Any:
    """Normalize a completion_gate dictionary, preserving all valid confirm and watch fields."""
    if not isinstance(gate, dict):
        return gate

    result = copy.deepcopy(gate)
    vision = result.get("vision") or result.get("vision_confirm")
    if isinstance(vision, dict):
        legacy_keys: list[str] = []
        if "camera_ids" in vision:
            legacy_keys.append("camera_ids")
        if "description" in vision:
            legacy_keys.append("description")

        if legacy_keys:
            logger.warning(
                "legacy_vision_gate_keys_ignored",
                legacy_keys=legacy_keys,
            )
            for k in legacy_keys:
                vision.pop(k, None)

        new_vision: dict[str, Any] = {}
        if "gate_graph_rule_id" in vision:
            new_vision["gate_graph_rule_id"] = vision["gate_graph_rule_id"]

        confirm = vision.get("confirm")
        if isinstance(confirm, dict):
            new_vision["confirm"] = {k: confirm.get(k) for k in _CONFIRM_KEYS}
        elif "confirm" in vision:
            new_vision["confirm"] = confirm

        watch = vision.get("watch")
        if isinstance(watch, dict):
            new_vision["watch"] = {k: watch.get(k) for k in _WATCH_KEYS}
        elif "watch" in vision:
            new_vision["watch"] = watch

        for k, val in vision.items():
            if k not in {"confirm", "watch", "gate_graph_rule_id", "camera_ids", "description"}:
                new_vision[k] = val

        result["vision"] = new_vision
        if "vision_confirm" in result:
            result.pop("vision_confirm", None)

    return result
