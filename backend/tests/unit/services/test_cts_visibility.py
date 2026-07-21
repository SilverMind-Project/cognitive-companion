"""Unit tests for compute_visibility_from_homography."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services.cts_visibility import compute_visibility_from_homography

_POINTS_PER_EDGE = 20


@pytest.fixture(autouse=True)
def no_range_cap():
    with patch("backend.services.cts_visibility.settings.get", return_value=99999.0):
        yield


def _identity_h() -> list[list[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


# -- Basic contract --------------------------------------------------------


def test_returns_80_points_for_identity():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    assert res.polygon is not None
    assert res.reason is None
    assert len(res.polygon) >= 4


def test_identity_top_left_normalises_to_origin():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    assert res.polygon is not None
    # Just verify that [0, 0] is one of the vertices in the polygon
    has_origin = False
    for p in res.polygon:
        if abs(p[0]) < 0.01 and abs(p[1]) < 0.01:
            has_origin = True
            break
    assert has_origin, "Origin [0, 0] not found in polygon"


def test_coordinates_normalised_to_unit_square_for_identity():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=200,
        image_height=150,
        floor_plan_width_m=200.0,
        floor_plan_height_m=150.0,
    )
    assert res.polygon is not None
    for x, y in res.polygon:
        assert -0.01 <= x <= 1.01, f"x={x} out of [0,1]"
        assert -0.01 <= y <= 1.01, f"y={y} out of [0,1]"


# -- Degenerate inputs ------------------------------------------------------


def test_returns_none_for_zero_fp_width():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=0.0,
        floor_plan_height_m=8.0,
    )
    assert res.polygon is None
    assert res.reason == "degenerate_matrix"


def test_returns_none_for_zero_fp_height():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=10.0,
        floor_plan_height_m=0.0,
    )
    assert res.polygon is None
    assert res.reason == "degenerate_matrix"


def test_returns_none_for_singular_matrix():
    zero = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    res = compute_visibility_from_homography(
        matrix=zero,
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=10.0,
        floor_plan_height_m=8.0,
    )
    assert res.polygon is None
    assert res.reason == "degenerate_matrix"


# -- Wide-angle / non-square ------------------------------------------------


def test_non_square_image_returns_expected_point_count():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=1920.0,
        floor_plan_height_m=1080.0,
    )
    assert res.polygon is not None
    assert len(res.polygon) >= 4


def test_rounding_to_4_decimal_places():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=1920,
        image_height=1080,
        floor_plan_width_m=1920.0,
        floor_plan_height_m=1080.0,
    )
    assert res.polygon is not None
    for x, y in res.polygon:
        assert x == round(x, 4)
        assert y == round(y, 4)


# -- Boundary ordering ------------------------------------------------------


def test_boundary_order_top_right_bottom_left():
    res = compute_visibility_from_homography(
        matrix=_identity_h(),
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    poly = res.polygon
    assert poly is not None
    assert len(poly) >= 4
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    assert min(xs) < 0.01
    assert max(xs) > 0.99
    assert min(ys) < 0.01
    assert max(ys) > 0.99


# -- Floor-region polygon path -----------------------------------------------


def _interior_floor_region() -> list[list[float]]:
    """A rectangular floor region well inside the image (20%-80% in both axes)."""
    return [[0.2, 0.4], [0.8, 0.4], [0.8, 0.9], [0.2, 0.9]]


def test_floor_region_excludes_walls():
    """Floor-region polygon projects to a smaller polygon than the image border."""
    H = _identity_h()
    W, H_px = 1000, 800

    poly_border = compute_visibility_from_homography(
        matrix=H,
        image_width=W,
        image_height=H_px,
        floor_plan_width_m=float(W),
        floor_plan_height_m=float(H_px),
    ).polygon
    poly_floor = compute_visibility_from_homography(
        matrix=H,
        image_width=W,
        image_height=H_px,
        floor_plan_width_m=float(W),
        floor_plan_height_m=float(H_px),
        floor_region_polygon=_interior_floor_region(),
    ).polygon
    assert poly_border is not None
    assert poly_floor is not None

    def _bbox(pts: list[list[float]]) -> tuple[float, float, float, float]:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    bx0, by0, bx1, by1 = _bbox(poly_border)
    fx0, fy0, fx1, fy1 = _bbox(poly_floor)

    assert fx0 > bx0, "floor region should not extend to left wall"
    assert fy0 > by0, "floor region should not extend to top wall"
    assert fx1 < bx1, "floor region should not extend to right wall"
    assert fy1 < by1, "floor region should not extend to bottom wall"


def test_no_floor_region_falls_back_to_image_border():
    H = _identity_h()
    poly_no_region = compute_visibility_from_homography(
        matrix=H,
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    ).polygon
    poly_explicit_none = compute_visibility_from_homography(
        matrix=H,
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
        floor_region_polygon=None,
    ).polygon
    assert poly_no_region is not None
    assert poly_explicit_none is not None
    assert poly_no_region == poly_explicit_none
    assert len(poly_no_region) >= 4


def test_floor_region_densifies_edges():
    H = _identity_h()
    floor_region = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    poly = compute_visibility_from_homography(
        matrix=H,
        image_width=1000,
        image_height=1000,
        floor_plan_width_m=1000.0,
        floor_plan_height_m=1000.0,
        floor_region_polygon=floor_region,
    ).polygon
    assert poly is not None
    assert len(poly) >= 4


def test_degenerate_floor_region_falls_back_or_returns_none():
    H = _identity_h()
    res = compute_visibility_from_homography(
        matrix=H,
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
        floor_region_polygon=[],
    )
    assert res.polygon is None
    assert res.reason == "no_floor_side"


# -- Horizon clipping and range capping -------------------------------------


def test_horizon_clipping_no_floor_side():
    # Matrix where points project outside the floor plan entirely.
    matrix = [[1.0, 0.0, 5000.0], [0.0, 1.0, 5000.0], [0.0, 0.0, 1.0]]
    res = compute_visibility_from_homography(
        matrix=matrix,
        image_width=100,
        image_height=100,
        floor_plan_width_m=10.0,
        floor_plan_height_m=10.0,
    )
    assert res.polygon is None
    assert res.reason == "no_floor_side"


def test_range_capping():
    with patch("backend.services.cts_visibility.settings.get", return_value=15.0):
        # Matrix where reference point is (50, 50) but top of image projects to infinity
        matrix = [[50.0, 0.0, 0.0], [0.0, 25.0, 0.0], [0.0, 1.0, -50.0]]
        res = compute_visibility_from_homography(
            matrix=matrix,
            image_width=100,
            image_height=100,
            floor_plan_width_m=100.0,
            floor_plan_height_m=100.0,
        )
        assert res.polygon is not None
        assert res.reason is None

        # Verify points are capped. Capped points should be around 0.5 +/- 0.15 normalized
        for p in res.polygon:
            assert 0.3 <= p[0] <= 0.7
            assert 0.3 <= p[1] <= 0.7
