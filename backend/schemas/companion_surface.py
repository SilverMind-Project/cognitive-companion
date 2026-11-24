"""HTTP schemas for companion surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.companion_surface_ws import SurfacePlatform

SurfaceType = Literal["fixed", "movable"]
SurfaceKind = Literal["tablet", "speaker", "display", "tv"]
RoomSource = Literal["caregiver", "cts_inferred"]


class CompanionSurfaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    surface_type: SurfaceType
    room_id: int | None = None
    kind: SurfaceKind
    is_enabled: bool = True


class CompanionSurfaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    surface_type: SurfaceType | None = None
    room_id: int | None = None
    kind: SurfaceKind | None = None
    is_enabled: bool | None = None


class CompanionSurfaceHeartbeat(BaseModel):
    """A surface's periodic check-in, with the device state it can report.

    Whether a face is in front of the screen is deliberately not accepted here:
    it is a fact about the resident, not the device, and is never stored.
    """

    model_config = ConfigDict(extra="forbid")

    reported_room_id: int | None = None
    platform: SurfacePlatform | None = None
    mic_active: bool | None = None
    camera_active: bool | None = None
    screen_awake: bool | None = None


class CompanionSurfaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    surface_type: SurfaceType
    room_id: int | None
    room_source: RoomSource
    kind: SurfaceKind
    is_enabled: bool
    last_seen_at: datetime | None
    room_mismatch: bool
    platform: SurfacePlatform | None = None
    mic_active: bool | None = None
    camera_active: bool | None = None
    screen_awake: bool | None = None
    created_at: datetime
    updated_at: datetime


class CompanionSurfaceListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CompanionSurfaceOut]
    total: int


class CompanionSurfaceTestIn(BaseModel):
    """Ask one screen to identify itself (wake, chime, a short lease)."""

    model_config = ConfigDict(extra="forbid")

    microphone: bool = Field(
        default=False,
        description="Also open the screen's microphone for the lease, to check it listens.",
    )


class CompanionSurfaceTestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_id: str
    reached: int = Field(description="Live connections the command reached; 0 means offline.")
    microphone: bool
    lease_seconds: int


class CompanionSurfaceHeartbeatOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
