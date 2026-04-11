from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import UTCDatetime


class RoomCreate(BaseModel):
    name: str
    ha_area_id: str | None = None
    floor: str | None = None
    metadata_json: dict[str, Any] | None = None


class RoomUpdate(BaseModel):
    name: str | None = None
    ha_area_id: str | None = None
    floor: str | None = None
    metadata_json: dict[str, Any] | None = None


class RoomOut(BaseModel):
    id: int
    name: str
    ha_area_id: str | None
    floor: str | None
    metadata_json: dict[str, Any] | None
    created_at: UTCDatetime

    model_config = {"from_attributes": True}
