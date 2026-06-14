"""Monotonic cooldown tracking shared by camera aggregators."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from types import MappingProxyType


class CooldownTracker:
    """Tracks monotonic cooldown deadlines keyed by an arbitrary string."""

    def __init__(self, time_fn: Callable[[], float] = time.monotonic) -> None:
        self._time = time_fn
        self._deadlines: dict[str, float] = {}

    @property
    def deadlines(self) -> Mapping[str, float]:
        """Expose deadlines read-only for transitional compatibility."""
        return MappingProxyType(self._deadlines)

    def arm(self, key: str, seconds: float) -> None:
        """Set a cooldown deadline relative to the current monotonic time."""
        self._deadlines[key] = self._time() + seconds

    def active(self, key: str) -> bool:
        """Return whether a key is still inside its cooldown period."""
        deadline = self._deadlines.get(key)
        return deadline is not None and self._time() < deadline

    def remaining(self, key: str) -> float | None:
        """Return rounded seconds remaining, or None when inactive."""
        deadline = self._deadlines.get(key)
        if deadline is None:
            return None
        remaining = deadline - self._time()
        return round(remaining, 1) if remaining > 0 else None
