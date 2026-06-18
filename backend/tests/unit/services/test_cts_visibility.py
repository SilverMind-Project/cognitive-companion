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


# -- Floor-region polygon path -----------------------------------------------


def _interior_floor_region() -> list[list[float]]:
    """A rectangular floor region well inside the image (20%-80% in both axes)."""
    return [[0.2, 0.4], [0.8, 0.4], [0.8, 0.9], [0.2, 0.9]]


def test_floor_region_excludes_walls():
    """Floor-region polygon projects to a smaller polygon than the image border.

    The image border includes wall pixels that project to extreme / spurious
    floor coordinates.  An interior floor region should yield a tighter polygon.
    """
    H = _identity_h()
    W, H_px = 1000, 800

    poly_border = compute_visibility_from_homography(
        matrix=H,
        image_width=W,
        image_height=H_px,
        floor_plan_width_m=float(W),
        floor_plan_height_m=float(H_px),
    )
    poly_floor = compute_visibility_from_homography(
        matrix=H,
        image_width=W,
        image_height=H_px,
        floor_plan_width_m=float(W),
        floor_plan_height_m=float(H_px),
        floor_region_polygon=_interior_floor_region(),
    )
    assert poly_border is not None
    assert poly_floor is not None

    def _bbox(pts: list[list[float]]) -> tuple[float, float, float, float]:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    bx0, by0, bx1, by1 = _bbox(poly_border)
    fx0, fy0, fx1, fy1 = _bbox(poly_floor)

    # Floor polygon is strictly within the border polygon bounds.
    assert fx0 > bx0, "floor region should not extend to left wall"
    assert fy0 > by0, "floor region should not extend to top wall"
    assert fx1 < bx1, "floor region should not extend to right wall"
    assert fy1 < by1, "floor region should not extend to bottom wall"


def test_no_floor_region_falls_back_to_image_border():
    """Backward-compat: without floor_region_polygon the output matches prior behavior."""
    H = _identity_h()
    poly_no_region = compute_visibility_from_homography(
        matrix=H,
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
    )
    poly_explicit_none = compute_visibility_from_homography(
        matrix=H,
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
        floor_region_polygon=None,
    )
    assert poly_no_region is not None
    assert poly_explicit_none is not None
    assert poly_no_region == poly_explicit_none
    assert len(poly_no_region) == 4 * _POINTS_PER_EDGE


def test_floor_region_densifies_edges():
    """Edges of the floor-region polygon must be densified to capture lens distortion."""
    H = _identity_h()
    # Long edge from (0,0) to (1,0): 1000 px wide, step=10 px -> ~100 points just on that edge.
    floor_region = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    poly = compute_visibility_from_homography(
        matrix=H,
        image_width=1000,
        image_height=1000,
        floor_plan_width_m=1000.0,
        floor_plan_height_m=1000.0,
        floor_region_polygon=floor_region,
    )
    assert poly is not None
    # Four edges of 1000 px each, step=10 -> ~100 samples per edge -> ~400 total.
    assert len(poly) > 4 * _POINTS_PER_EDGE, (
        f"densified floor region should produce more points than image-border fallback "
        f"({4 * _POINTS_PER_EDGE}), got {len(poly)}"
    )


def test_degenerate_floor_region_falls_back_or_returns_none():
    """A degenerate (empty) floor_region_polygon is handled gracefully."""
    H = _identity_h()
    # An empty list should produce an empty boundary and return None.
    result = compute_visibility_from_homography(
        matrix=H,
        image_width=100,
        image_height=100,
        floor_plan_width_m=100.0,
        floor_plan_height_m=100.0,
        floor_region_polygon=[],
    )
    # Empty polygon -> empty boundary -> no points to project -> None.
    assert result is None
