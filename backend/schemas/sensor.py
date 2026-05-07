from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator

from backend.schemas.common import UTCDatetime


def _validate_movement_map_in_config(config_json: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate movement_map key inside config_json if present."""
    if config_json is None:
        return None
    movement_map = config_json.get("movement_map")
    if movement_map is not None:
        from backend.schemas.sensor_config import MovementMap
        MovementMap.model_validate(movement_map)
    return config_json


class SensorCreate(BaseModel):
    id: str
    name: str
    room_id: int | None = None
    sensor_type: str = "camera"
    source: str = "local"
    ha_entity_id: str | None = None
    enabled: bool = True
    config_json: dict[str, Any] | None = None

    @field_validator("config_json")
    @classmethod
    def _check_config_json(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_movement_map_in_config(v)


class SensorUpdate(BaseModel):
    name: str | None = None
    room_id: int | None = None
    sensor_type: str | None = None
    source: str | None = None
    ha_entity_id: str | None = None
    enabled: bool | None = None
    config_json: dict[str, Any] | None = None

    @field_validator("config_json")
    @classmethod
    def _check_config_json(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return _validate_movement_map_in_config(v)


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
