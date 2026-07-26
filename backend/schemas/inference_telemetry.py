"""Response envelope for LLM admission-control telemetry (DL-M09)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CallerLaneOutcomeOut(BaseModel):
    """Call counts for one (caller, lane) pair over the reporting window."""

    model_config = ConfigDict(extra="forbid")

    caller: str
    lane: str
    ok: int
    timeout: int
    error: int


class HourlyCallBucketOut(BaseModel):
    """Calls started in one UTC hour bucket, per lane."""

    model_config = ConfigDict(extra="forbid")

    hour: str  # ISO 8601 UTC hour start, e.g. "2026-07-26T14:00:00+00:00"
    lane: str
    calls: int


class QueueDepthOut(BaseModel):
    """Current (live) admissions waiting on a lane's semaphore."""

    model_config = ConfigDict(extra="forbid")

    lane: str
    depth: int


class InferenceTelemetryOut(BaseModel):
    """Admission-controller telemetry for the admin dashboard."""

    model_config = ConfigDict(extra="forbid")

    window_minutes: int
    totals_by_caller_lane: list[CallerLaneOutcomeOut]
    queue_depth: list[QueueDepthOut]
    queue_wait_p50_ms: float | None
    queue_wait_p95_ms: float | None
    timeouts_total: int
    calls_per_hour: list[HourlyCallBucketOut]
    ring_buffer_size: int
    ring_buffer_capacity: int
