"""HTTP schemas for companion surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SurfaceType = Literal["fixed", "movable"]
SurfaceKind = Literal["tablet", "speaker", "display"]
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
    model_config = ConfigDict(extra="forbid")

    reported_room_id: int | None = None


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
    created_at: datetime
    updated_at: datetime


class CompanionSurfaceListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CompanionSurfaceOut]
    total: int


class CompanionSurfaceHeartbeatOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
