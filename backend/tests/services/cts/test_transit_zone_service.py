"""WTR5: Transit zone validation tests."""
from __future__ import annotations

import pytest

from backend.services.cts.transit_zone_service import validate_transit_zone_polygon


def test_valid_polygon_passes():
    """A valid polygon with distinct rooms passes validation."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]],
        inside_room_id=1,
        outside_room_id=2,
        direction_vec=[1.0, 0.0],
    )
    assert errors == []


def test_self_intersecting_polygon_rejected():
    """A self-intersecting (bow-tie) polygon is rejected."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [2.0, 2.0], [0.0, 2.0], [2.0, 0.0]],
        inside_room_id=1,
        outside_room_id=2,
        direction_vec=[1.0, 0.0],
    )
    assert len(errors) > 0


def test_zero_area_polygon_rejected():
    """A degenerate (collinear) polygon with zero area is rejected."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
        inside_room_id=1,
        outside_room_id=2,
        direction_vec=[1.0, 0.0],
    )
    assert len(errors) > 0


def test_too_few_vertices_rejected():
    """Less than 3 vertices is rejected."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [1.0, 1.0]],
        inside_room_id=1,
        outside_room_id=2,
        direction_vec=[1.0, 0.0],
    )
    assert len(errors) > 0
    assert any("vertices" in e for e in errors)


def test_same_inside_outside_room_rejected():
    """inside_room_id == outside_room_id must be rejected."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]],
        inside_room_id=1,
        outside_room_id=1,
        direction_vec=[1.0, 0.0],
    )
    assert len(errors) > 0
    assert any("different" in e for e in errors)


def test_missing_room_ids_rejected():
    """Missing room ids must be rejected."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]],
        direction_vec=[1.0, 0.0],
    )
    assert len(errors) > 0


def test_zero_direction_vector_rejected():
    """A zero-magnitude direction vector must be rejected."""
    errors = validate_transit_zone_polygon(
        polygon=[[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]],
        inside_room_id=1,
        outside_room_id=2,
        direction_vec=[0.0, 0.0],
    )
    assert len(errors) > 0
