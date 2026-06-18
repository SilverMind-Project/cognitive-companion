"""HTTP schemas for sub-room zones."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RoomZoneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    purpose: str | None = Field(default=None, max_length=32)
    polygon: list[list[float]] = Field(min_length=3)
    camera_ids: list[str] | None = None
    is_enabled: bool = True


class RoomZoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    purpose: str | None = Field(default=None, max_length=32)
    polygon: list[list[float]] | None = Field(default=None, min_length=3)
    camera_ids: list[str] | None = None
    is_enabled: bool | None = None


class RoomZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    name: str
    purpose: str | None
    polygon: list[list[float]]
    camera_ids: list[str] | None
    is_enabled: bool


class RoomZoneListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RoomZoneOut]
    total: int
