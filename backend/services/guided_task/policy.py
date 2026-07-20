"""Guided-task policy resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.services.guided_task.domain import ResolvedPolicy


def resolve_vision_override(
    val: Any | None,
    *,
    settings: Any,
    settings_path: str,
    cast: Callable[[Any], Any] = lambda v: v,
    default: Any = None,
) -> Any:
    """Resolve one nested ``guided_task.vision.*`` setting.

    Precedence: per-step override, ``config/settings.yaml``
    global, then ``default``.
    """
    if val is not None:
        return cast(val)
    if settings is not None:
        try:
            settings_val = settings.get(settings_path)
        except Exception:  # noqa: BLE001
            settings_val = None
        if settings_val is not None:
            return cast(settings_val)
    return default


def _pick(step_val: int | None, routine_val: int | None, global_val: int) -> int:
    if step_val is not None:
        return step_val
    if routine_val is not None:
        return routine_val
    return global_val


def resolve_policy(routine: Any, step: Any, settings: Any) -> ResolvedPolicy:
    """Resolve guided_task policy with precedence: step, routine, global.

    A None override at a level falls through to the next level. Global values
    come from ``config/settings.yaml`` under ``guided_task.*``.
    """
    return ResolvedPolicy(
        step_timeout_s=_pick(
            step.step_timeout_s_override,
            routine.step_timeout_s_override,
            settings.as_int("guided_task.step_timeout_s"),
        ),
        max_step_attempts=_pick(
            step.max_step_attempts_override,
            routine.max_step_attempts_override,
            settings.as_int("guided_task.max_step_attempts"),
        ),
        resume_grace_s=_pick(
            None,
            routine.resume_grace_s_override,
            settings.as_int("guided_task.resume_grace_s"),
        ),
    )
