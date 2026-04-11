from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import UTCDatetime


class SensorCreate(BaseModel):
    id: str
    name: str
    room_id: int | None = None
    sensor_type: str = "camera"
    source: str = "local"
    ha_entity_id: str | None = None
    enabled: bool = True
    config_json: dict[str, Any] | None = None


class SensorUpdate(BaseModel):
    name: str | None = None
    room_id: int | None = None
    sensor_type: str | None = None
    source: str | None = None
    ha_entity_id: str | None = None
    enabled: bool | None = None
    config_json: dict[str, Any] | None = None


class SensorOut(BaseModel):
    id: str
    name: str
    room_id: int | None
    sensor_type: str
    source: str
    ha_entity_id: str | None
    enabled: bool
    config_json: dict[str, Any] | None
    created_at: UTCDatetime

    model_config = {"from_attributes": True}
