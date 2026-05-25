"""Pydantic models for Sensor.config_json validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

_VALID_SEMANTICS = Literal[
    "entering",
    "exiting",
    "approaching_exit",
    "entering_depth",
    "stationary",
]


class MovementMapEntry(BaseModel):
    """A single direction-to-semantic mapping for a camera sensor."""

    model_config = {"extra": "forbid"}

    semantic: _VALID_SEMANTICS
    from_room_id: int | None = None
    from_room_name: str | None = None
    to_room_id: int | None = None
    to_room_name: str | None = None


class MovementMap(BaseModel):
    """Movement map for a camera sensor's config_json.

    Validates that direction keys are from the known set so typos
    like ``left-to-righ`` are rejected at save time.
    Uses Pydantic aliases to map hyphenated JSON keys to Python identifiers.
    """

    model_config = {"extra": "forbid", "populate_by_name": True}

    left_to_right: MovementMapEntry | None = Field(
        default=None,
        alias="left-to-right",
        description="Direction: person moving left to right across the camera view.",
    )
    right_to_left: MovementMapEntry | None = Field(
        default=None,
        alias="right-to-left",
        description="Direction: person moving right to left across the camera view.",
    )
    towards_camera: MovementMapEntry | None = Field(
        default=None,
        alias="towards-camera",
        description="Direction: person walking towards the camera.",
    )
    away_from_camera: MovementMapEntry | None = Field(
        default=None,
        alias="away-from-camera",
        description="Direction: person walking away from the camera.",
    )
    stationary: MovementMapEntry | None = Field(
        default=None, alias="stationary", description="Direction: person standing still."
    )

    def to_json_dict(self) -> dict:
        """Export back to the JSON shape using hyphenated keys."""
        result: dict = {}
        for field_name, field_info in type(self).model_fields.items():
            value = getattr(self, field_name)
            alias = field_info.alias or field_name
            if value is not None:
                if isinstance(value, MovementMapEntry):
                    result[alias] = value.model_dump(exclude_none=True)
                else:
                    result[alias] = value
        return result


def validate_movement_map(data: dict | None) -> MovementMap | None:
    """Parse and validate a movement_map dict, returning None if absent or invalid."""
    if data is None:
        return None
    try:
        return MovementMap.model_validate(data)
    except ValidationError:
        return None
