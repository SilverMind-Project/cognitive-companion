"""Tests for floor-meter room-zone geometry helpers."""

from __future__ import annotations

from backend.services.zones.geometry import point_in_polygon


def test_point_inside_square_polygon_true() -> None:
    assert point_in_polygon((1.0, 1.0), [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])


def test_point_outside_polygon_false() -> None:
    assert not point_in_polygon((3.0, 3.0), [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])


def test_point_on_edge_is_inside() -> None:
    assert point_in_polygon((2.0, 1.0), [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])


def test_degenerate_polygon_fewer_than_3_points_false() -> None:
    assert not point_in_polygon((1.0, 1.0), [[0.0, 0.0], [2.0, 0.0]])


def test_concave_polygon_containment() -> None:
    polygon = [[0.0, 0.0], [3.0, 0.0], [3.0, 1.0], [1.0, 1.0], [1.0, 3.0], [0.0, 3.0]]

    assert point_in_polygon((0.5, 2.0), polygon)
    assert not point_in_polygon((2.0, 2.0), polygon)
