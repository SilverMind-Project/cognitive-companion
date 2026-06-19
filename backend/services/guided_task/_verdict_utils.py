"""Shared utility functions for vision gate and task completion verdicts."""

from typing import Any


def _bounded_float(value: Any) -> float:
    """Clamps a value converted to float between 0.0 and 1.0.

    If conversion fails, returns 0.0.
    """
    if value is None:
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, parsed))
