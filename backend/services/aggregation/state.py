"""Uniform runtime state contracts for camera aggregators."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

Origin = Literal["recamera", "cts"]


class CameraBufferState(BaseModel):
    """Uniform per-camera snapshot of an aggregator's runtime state."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str
    origin: Origin
    buffer_depth: int
    buffer_capacity: int | None = None
    pending_flush: int | None = None
    cooldown_remaining_seconds: float | None = None
    rate_per_second: float | None = None
    tokens_available: float | None = None
    images_eligible_total: int = 0
    images_dropped_total: int = 0
    last_event_at: str | None = None


@runtime_checkable
class AggregatorStatsProvider(Protocol):
    """Provides per-camera runtime state for aggregator observability."""

    def buffer_state(self) -> list[CameraBufferState]: ...
