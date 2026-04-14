"""Unit tests for :mod:`backend.services.camera_topology`.

All functions are pure (no I/O) so every branch can be exercised with
plain dict inputs and no mocks.
"""

from __future__ import annotations

import pytest

from backend.services.camera_topology import (
    SEMANTIC_ENTERING,
    SEMANTIC_ENTERING_DEPTH,
    SEMANTIC_EXITING,
    RoomTransition,
    infer_room_transition,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_BASE_KWARGS = {
    "person_id": "person-1",
    "person_name": "Alice",
    "sensor_id": "cam-kitchen",
    "confidence": 0.92,
}


def _make_config(movement_map: dict) -> dict:
    return {"movement_map": movement_map}


def _doorway_map() -> dict:
    """Canonical two-direction movement_map for a kitchen doorway camera."""
    return {
        "left-to-right": {
            "semantic": SEMANTIC_ENTERING,
            "from_room_id": 2,
            "from_room_name": "Hallway",
            "to_room_id": 1,
            "to_room_name": "Kitchen",
        },
        "right-to-left": {
            "semantic": SEMANTIC_EXITING,
            "from_room_id": 1,
            "from_room_name": "Kitchen",
            "to_room_id": 2,
            "to_room_name": "Hallway",
        },
    }


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_room_transition(self):
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="left-to-right",
            sensor_config=_make_config(_doorway_map()),
        )
        assert isinstance(result, RoomTransition)

    def test_entering_fields(self):
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="left-to-right",
            sensor_config=_make_config(_doorway_map()),
        )
        assert result.semantic == SEMANTIC_ENTERING
        assert result.from_room_id == 2
        assert result.from_room_name == "Hallway"
        assert result.to_room_id == 1
        assert result.to_room_name == "Kitchen"
        assert result.confidence == 0.92
        assert result.person_id == "person-1"
        assert result.person_name == "Alice"
        assert result.sensor_id == "cam-kitchen"
        assert result.direction_raw == "left-to-right"

    def test_exiting_fields(self):
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="right-to-left",
            sensor_config=_make_config(_doorway_map()),
        )
        assert result.semantic == SEMANTIC_EXITING
        assert result.from_room_id == 1
        assert result.from_room_name == "Kitchen"
        assert result.to_room_id == 2
        assert result.to_room_name == "Hallway"

    def test_nullable_room_ids_allowed(self):
        """Partial transitions (e.g. approaching_exit) may have None for to_room."""
        config = _make_config(
            {
                "towards-camera": {
                    "semantic": "approaching_exit",
                    "from_room_id": 1,
                    "from_room_name": "Kitchen",
                    "to_room_id": None,
                    "to_room_name": None,
                }
            }
        )
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="towards-camera",
            sensor_config=config,
        )
        assert result is not None
        assert result.to_room_id is None
        assert result.to_room_name is None
        assert result.from_room_id == 1

    def test_entering_depth_semantic(self):
        config = _make_config(
            {
                "away-from-camera": {
                    "semantic": SEMANTIC_ENTERING_DEPTH,
                    "from_room_id": None,
                    "from_room_name": None,
                    "to_room_id": 1,
                    "to_room_name": "Kitchen",
                }
            }
        )
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="away-from-camera",
            sensor_config=config,
        )
        assert result is not None
        assert result.semantic == SEMANTIC_ENTERING_DEPTH

    def test_to_dict_serialises_all_fields(self):
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="left-to-right",
            sensor_config=_make_config(_doorway_map()),
        )
        d = result.to_dict()
        assert d["person_id"] == "person-1"
        assert d["person_name"] == "Alice"
        assert d["sensor_id"] == "cam-kitchen"
        assert d["direction_raw"] == "left-to-right"
        assert d["semantic"] == SEMANTIC_ENTERING
        assert d["from_room_id"] == 2
        assert d["from_room_name"] == "Hallway"
        assert d["to_room_id"] == 1
        assert d["to_room_name"] == "Kitchen"
        assert d["confidence"] == 0.92


# ---------------------------------------------------------------------------
# Returns-None cases
# ---------------------------------------------------------------------------


class TestReturnsNone:
    def test_none_when_direction_raw_is_none(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw=None,
                sensor_config=_make_config(_doorway_map()),
            )
            is None
        )

    def test_none_when_direction_raw_is_empty_string(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="",
                sensor_config=_make_config(_doorway_map()),
            )
            is None
        )

    def test_none_when_direction_is_stationary(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="stationary",
                sensor_config=_make_config(_doorway_map()),
            )
            is None
        )

    def test_none_when_sensor_config_is_none(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="left-to-right",
                sensor_config=None,
            )
            is None
        )

    def test_none_when_sensor_config_is_empty_dict(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="left-to-right",
                sensor_config={},
            )
            is None
        )

    def test_none_when_movement_map_is_empty(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="left-to-right",
                sensor_config={"movement_map": {}},
            )
            is None
        )

    def test_none_when_direction_not_in_map(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="unknown-direction",
                sensor_config=_make_config(_doorway_map()),
            )
            is None
        )

    def test_none_when_mapping_is_not_a_dict(self):
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="left-to-right",
                sensor_config={"movement_map": {"left-to-right": "bad_value"}},
            )
            is None
        )

    def test_none_when_semantic_is_unknown(self):
        config = _make_config(
            {
                "left-to-right": {
                    "semantic": "teleporting",  # not a valid semantic
                    "from_room_id": 1,
                    "from_room_name": "Kitchen",
                    "to_room_id": 2,
                    "to_room_name": "Hallway",
                }
            }
        )
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="left-to-right",
                sensor_config=config,
            )
            is None
        )

    def test_none_when_semantic_is_missing(self):
        config = _make_config(
            {
                "left-to-right": {
                    # "semantic" key absent
                    "from_room_id": 1,
                    "from_room_name": "Kitchen",
                    "to_room_id": 2,
                    "to_room_name": "Hallway",
                }
            }
        )
        assert (
            infer_room_transition(
                **_BASE_KWARGS,
                direction_raw="left-to-right",
                sensor_config=config,
            )
            is None
        )


# ---------------------------------------------------------------------------
# RoomTransition is immutable
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_room_transition_is_frozen(self):
        result = infer_room_transition(
            **_BASE_KWARGS,
            direction_raw="left-to-right",
            sensor_config=_make_config(_doorway_map()),
        )
        with pytest.raises(AttributeError):
            result.person_id = "other"  # type: ignore[misc]
