"""Shared aggregation primitives for camera event services."""

from __future__ import annotations

from backend.services.aggregation.cooldown import CooldownTracker
from backend.services.aggregation.rate_limiter import PerCameraRateLimiter
from backend.services.aggregation.state import (
    AggregatorStatsProvider,
    CameraBufferState,
    Origin,
)

__all__ = [
    "AggregatorStatsProvider",
    "CameraBufferState",
    "CooldownTracker",
    "Origin",
    "PerCameraRateLimiter",
]
