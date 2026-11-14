"""Uniform runtime state contracts for camera aggregators."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

Origin = Literal["recamera", "cts"]
BufferKind = Literal["sliding_window", "batch"]


class CameraBufferState(BaseModel):
    """Uniform per-camera snapshot of an aggregator's runtime state."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str
    origin: Origin
    buffer_kind: BufferKind
    buffer_depth: int
    buffer_capacity: int | None = None
    pending_flush: int | None = None
    cooldown_remaining_seconds: float | None = None
    rate_per_second: float | None = None
    tokens_available: float | None = None
    images_eligible_total: int = 0
    images_dropped_total: int = Field(
        default=0,
        description="Images refused by the per-camera image rate limiter.",
    )
    last_event_at: str | None = None


@runtime_checkable
class AggregatorStatsProvider(Protocol):
    """Provides per-camera runtime state for aggregator observability."""

    def buffer_state(self) -> list[CameraBufferState]: ...
