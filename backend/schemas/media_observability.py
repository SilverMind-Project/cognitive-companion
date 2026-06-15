"""Response envelopes for media and aggregator observability."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class CameraAggregatorStateOut(BaseModel):
    """Enriched runtime state for one camera aggregator."""

    model_config = ConfigDict(extra="forbid")

    camera_id: str
    origin: Literal["recamera", "cts"]
    display_name: str | None
    room_name: str | None
    buffer_depth: int
    buffer_capacity: int | None
    pending_flush: int | None
    cooldown_remaining_seconds: float | None
    rate_per_second: float | None
    tokens_available: float | None
    images_eligible_total: int
    images_dropped_total: int
    last_event_at: str | None


class AggregatorStateListEnvelope(BaseModel):
    """Paginated camera aggregator state."""

    model_config = ConfigDict(extra="forbid")

    items: list[CameraAggregatorStateOut]
    total: int


class MediaBufferImageOut(BaseModel):
    """One retained image from the reCamera media cache."""

    model_config = ConfigDict(extra="forbid")

    id: int
    url: str
    object_name: str
    captured_at: str
    expires_at: str


class MediaBufferCameraOut(BaseModel):
    """Retained and pending media for one reCamera sensor."""

    model_config = ConfigDict(extra="forbid")

    sensor_id: str
    sensor_name: str
    room_name: str | None
    buffer_pending: int
    cooldown_remaining_seconds: float | None
    images: list[MediaBufferImageOut]


class MediaBufferListEnvelope(BaseModel):
    """Paginated reCamera media buffers."""

    model_config = ConfigDict(extra="forbid")

    items: list[MediaBufferCameraOut]
    total: int
