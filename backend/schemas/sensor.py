from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
    created_at: datetime

    model_config = {"from_attributes": True}
