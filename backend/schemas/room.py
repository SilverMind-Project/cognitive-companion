from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import OutSchema, UTCDatetime


class RoomFields(BaseModel):
    """Shared editable fields for Room create / update / output."""

    name: str
    ha_area_id: str | None = None
    floor: str | None = None
    metadata_json: dict[str, Any] | None = None
    floor_polygon: list[list[float]] | None = None


class RoomCreate(RoomFields):
    pass


class RoomUpdate(BaseModel):
    name: str | None = None
    ha_area_id: str | None = None
    floor: str | None = None
    metadata_json: dict[str, Any] | None = None
    floor_polygon: list[list[float]] | None = None


class RoomOut(RoomFields, OutSchema):
    id: int
    created_at: UTCDatetime
