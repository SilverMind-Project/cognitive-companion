"""Single-source completion_gate structure normalization.

Imported by both backend.schemas.guided_task (Pydantic input validation)
and backend.services.guided_task.routine_admin (service persistence) so
the allowed confirm/watch keys never drift between layers.
"""

from __future__ import annotations

import copy
from typing import Any

from backend.core.logging import get_logger
from backend.models.person import ActivityTypeEnum

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


ACTIVITY_TYPES: frozenset[str] = frozenset(member.value for member in ActivityTypeEnum)
# The activity evaluator's own default look-back.
DEFAULT_ACTIVITY_WINDOW_MINUTES = 10


def _canonical_activity(raw: dict[str, Any]) -> dict[str, Any]:
    """The ``activity`` sub-config in the one shape the evaluator reads.

    Older editors wrote ``window_s`` (seconds) and a free-text type; the
    evaluator never read ``window_s``, so a configured window silently became
    10 minutes, and an unknown type could never match a recorded activity.
    """
    activity_type = raw.get("activity_type") or raw.get("type")
    if not activity_type:
        raise ValueError("The activity gate needs an activity type.")
    if activity_type not in ACTIVITY_TYPES:
        raise ValueError(
            f"Unknown activity type {activity_type!r}; expected one of {sorted(ACTIVITY_TYPES)}."
        )
    window = raw.get("window_minutes", raw.get("within_minutes"))
    if window is None and raw.get("window_s") is not None:
        logger.warning("legacy_activity_gate_window_s_converted", window_s=raw["window_s"])
        window = float(raw["window_s"]) / 60
    window = DEFAULT_ACTIVITY_WINDOW_MINUTES if window is None else float(window)
    if window <= 0:
        raise ValueError("The activity gate's look-back window must be positive.")
    canonical: dict[str, Any] = {"activity_type": activity_type, "window_minutes": window}
    for key in ("min_confidence", "room_name"):
        if raw.get(key) is not None:
            canonical[key] = raw[key]
    return canonical


def _normalize_activity_and_zone(result: dict[str, Any]) -> None:
    """Canonicalize the activity and zone sub-configs in place.

    ``activity`` holds ``{activity_type, window_minutes}`` and ``zone_presence``
    holds ``{zone_id}``. The old ``zone`` key was never read, so the editor's
    target zone silently fell back to the step's zone.
    """
    raw_activity = result.pop("activity_signal", None)
    raw_activity = result.pop("activity", raw_activity)
    if "activity_signal" in (result.get("kinds") or []):
        # Only an enabled activity gate is validated and kept: a sub-config left
        # behind by unticking the kind is never evaluated, so it is dropped.
        result["activity"] = _canonical_activity(
            raw_activity if isinstance(raw_activity, dict) else {}
        )
    legacy_zone = result.pop("zone", None)
    if isinstance(legacy_zone, dict) and "zone_presence" not in result:
        result["zone_presence"] = {"zone_id": legacy_zone.get("zone_id")}


def normalize_completion_gate(gate: Any) -> Any:
    """Normalize a completion_gate dictionary, preserving all valid confirm and watch fields,
    and canonicalizing the activity and zone sub-configs."""
    if not isinstance(gate, dict):
        return gate

    result = copy.deepcopy(gate)
    _normalize_activity_and_zone(result)
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
