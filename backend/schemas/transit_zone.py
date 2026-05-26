"""Pydantic schemas for transit zones (M2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TransitZoneIn(BaseModel):
    """Create/update a transit zone."""

    name: str = Field(..., min_length=1, max_length=256)
    kind: str = Field(default="door", pattern="^(door|threshold)$")
    polygon: list[list[float]] = Field(..., min_length=3)
    inside_room_id: int
    outside_room_id: int
    direction_vec: list[float] = Field(..., min_length=2, max_length=2)

    class Config:
        extra = "forbid"


class TransitZoneUpdate(BaseModel):
    """Partial update for a transit zone."""

    name: str | None = Field(None, min_length=1, max_length=256)
    kind: str | None = Field(None, pattern="^(door|threshold)$")
    polygon: list[list[float]] | None = None
    inside_room_id: int | None = None
    outside_room_id: int | None = None
    direction_vec: list[float] | None = Field(None, min_length=2, max_length=2)

    class Config:
        extra = "forbid"


class TransitZoneOut(BaseModel):
    """Transit zone as returned to the frontend."""

    id: str
    name: str
    kind: str
    polygon: list[list[float]]
    inside_room_id: int
    outside_room_id: int
    direction_vec: list[float]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
