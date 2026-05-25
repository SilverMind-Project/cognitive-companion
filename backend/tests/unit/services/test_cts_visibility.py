"""Unit tests for compute_visibility_from_homography."""

from __future__ import annotations

from backend.services.cts_visibility import _POINTS_PER_EDGE, compute_visibility_from_homography


def _identity_h() -> list[list[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


# -- Basic contract --------------------------------------------------------


def test_returns_80_points_for_identity():
    poly = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    assert poly is not None
    assert len(poly) == 4 * _POINTS_PER_EDGE


def test_identity_top_left_normalises_to_origin():
    poly = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    assert poly is not None
    assert abs(poly[0][0]) < 0.01
    assert abs(poly[0][1]) < 0.01


def test_coordinates_normalised_to_unit_square_for_identity():
    poly = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=200,
        image_height=150,
        floor_plan_width_m=200.0,
        floor_plan_height_m=150.0,
    )
    assert poly is not None
    for x, y in poly:
        assert -0.01 <= x <= 1.01, f"x={x} out of [0,1]"
        assert -0.01 <= y <= 1.01, f"y={y} out of [0,1]"


# -- Degenerate inputs ------------------------------------------------------


def test_returns_none_for_zero_fp_width():
    result = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=0.0,
        floor_plan_height_m=8.0,
    )
    assert result is None


def test_returns_none_for_zero_fp_height():
    result = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=10.0,
        floor_plan_height_m=0.0,
    )
    assert result is None


def test_returns_none_for_singular_matrix():
    zero = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    result = compute_visibility_from_homography(
        matrix=zero,
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=10.0,
        floor_plan_height_m=8.0,
    )
    assert result is None


def test_returns_none_for_out_of_bounds_projection():
    far = [[100.0, 0.0, 0.0], [0.0, 100.0, 0.0], [0.0, 0.0, 1.0]]
    result = compute_visibility_from_homography(
        matrix=far,
        image_width=100,
        image_height=100,
        floor_plan_width_m=1.0,
        floor_plan_height_m=1.0,
    )
    assert result is None


# -- Wide-angle / non-square ------------------------------------------------


def test_non_square_image_returns_expected_point_count():
    poly = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=1920.0,
        floor_plan_height_m=1080.0,
    )
    assert poly is not None
    assert len(poly) == 4 * _POINTS_PER_EDGE


def test_rounding_to_4_decimal_places():
    poly = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=1920.0,
        floor_plan_height_m=1080.0,
    )
    assert poly is not None
    for x, y in poly:
        assert x == round(x, 4)
        assert y == round(y, 4)


# -- Boundary ordering ------------------------------------------------------


def test_boundary_order_top_right_bottom_left():
    poly = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    assert poly is not None
    n = _POINTS_PER_EDGE
    top_edge = poly[:n]
    right_edge = poly[n : 2 * n]
    bottom_edge = poly[2 * n : 3 * n]
    left_edge = poly[3 * n :]

    for _, y in top_edge:
        assert y < 0.01, f"Top edge point has y={y}"

    for x, _ in right_edge:
        assert x > 0.99, f"Right edge point has x={x}"

    for _, y in bottom_edge:
        assert y > 0.99, f"Bottom edge point has y={y}"

    for x, _ in left_edge:
        assert x < 0.01, f"Left edge point has x={x}"
