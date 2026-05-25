"""Tests for MovementMap schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.sensor_config import MovementMap, MovementMapEntry, validate_movement_map


class TestMovementMapEntry:
    def test_valid_entry(self):
        entry = MovementMapEntry(
            semantic="entering",
            from_room_id=1,
            from_room_name="Hallway",
            to_room_id=2,
            to_room_name="Kitchen",
        )
        assert entry.semantic == "entering"
        assert entry.from_room_id == 1

    def test_invalid_semantic_rejected(self):
        with pytest.raises(ValidationError):
            MovementMapEntry(semantic="invalid_direction", from_room_id=1)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            MovementMapEntry(semantic="entering", bogus_field="nope")


class TestMovementMap:
    def test_valid_full_map(self):
        data = {
            "left-to-right": {
                "semantic": "entering",
                "from_room_id": 2,
                "from_room_name": "Hallway",
                "to_room_id": 1,
                "to_room_name": "Kitchen",
            },
            "right-to-left": {
                "semantic": "exiting",
                "from_room_id": 1,
                "from_room_name": "Kitchen",
                "to_room_id": 2,
                "to_room_name": "Hallway",
            },
            "towards-camera": {
                "semantic": "approaching_exit",
                "from_room_id": 1,
                "from_room_name": "Kitchen",
            },
            "away-from-camera": {
                "semantic": "entering_depth",
                "to_room_id": 1,
                "to_room_name": "Kitchen",
            },
        }
        parsed = MovementMap.model_validate(data)
        assert parsed.left_to_right.semantic == "entering"
        assert parsed.right_to_left.semantic == "exiting"

    def test_unknown_direction_key_rejected(self):
        data = {"left-to-righ": {"semantic": "entering"}}
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            MovementMap.model_validate(data)

    def test_missing_semantic_rejected(self):
        data = {"left-to-right": {"from_room_id": 1}}
        with pytest.raises(ValidationError):
            MovementMap.model_validate(data)

    def test_empty_map_is_valid(self):
        parsed = MovementMap.model_validate({})
        assert parsed.left_to_right is None

    def test_stationary_mapping(self):
        data = {"stationary": {"semantic": "stationary"}}
        parsed = MovementMap.model_validate(data)
        assert parsed.stationary.semantic == "stationary"

    def test_to_json_dict(self):
        data = {"left-to-right": {"semantic": "entering", "from_room_id": 1}}
        parsed = MovementMap.model_validate(data)
        exported = parsed.to_json_dict()
        assert exported["left-to-right"]["semantic"] == "entering"

    def test_validate_movement_map_none(self):
        assert validate_movement_map(None) is None

    def test_validate_movement_map_empty(self):
        assert validate_movement_map({}) is not None


class TestSensorSchemaValidation:
    """Integration: SensorCreate/SensorUpdate validation of movement_map."""

    def test_create_with_valid_movement_map(self):
        from backend.schemas.sensor import SensorCreate

        s = SensorCreate(
            id="cam_01",
            name="Kitchen Cam",
            sensor_type="camera",
            config_json={
                "movement_map": {
                    "left-to-right": {"semantic": "entering", "from_room_id": 1, "to_room_id": 2},
                    "right-to-left": {"semantic": "exiting", "from_room_id": 2, "to_room_id": 1},
                }
            },
        )
        assert s.config_json is not None

    def test_create_with_typo_direction_rejected(self):
        from backend.schemas.sensor import SensorCreate

        with pytest.raises(ValidationError):
            SensorCreate(
                id="cam_01",
                name="Kitchen Cam",
                config_json={
                    "movement_map": {
                        "left-to-righ": {"semantic": "entering"},
                    }
                },
            )

    def test_create_with_invalid_semantic_rejected(self):
        from backend.schemas.sensor import SensorCreate

        with pytest.raises(ValidationError):
            SensorCreate(
                id="cam_01",
                name="Kitchen Cam",
                config_json={
                    "movement_map": {
                        "left-to-right": {"semantic": "leaving"},
                    }
                },
            )

    def test_create_without_movement_map_is_ok(self):
        from backend.schemas.sensor import SensorCreate

        s = SensorCreate(id="cam_01", name="Kitchen Cam", config_json={"foo": "bar"})
        assert s.config_json == {"foo": "bar"}

    def test_update_with_valid_movement_map(self):
        from backend.schemas.sensor import SensorUpdate

        s = SensorUpdate(
            config_json={
                "movement_map": {
                    "left-to-right": {"semantic": "entering"},
                }
            },
        )
        assert s.config_json is not None
