"""Derive camera visibility polygons from homography matrices.

compute_visibility_from_homography:
    Projects boundary points through the homography matrix H (pixel ->
    floor-plan metres) to get the floor-coverage polygon on the floor plan.

    When a ``floor_region_polygon`` (normalised [0,1] image-space polygon
    derived from depth auto-calibration or operator hand-drawing) is provided,
    the boundary is sampled **along the floor-region polygon edges** instead of
    the image border.  This excludes walls that project to meaningless floor
    coordinates.  When absent, falls back to the floor-side boundary.

    All returned coordinates are normalised to [0, 1] relative to the
    floor-plan image dimensions so the polygon is independent of floor-plan
    image resolution.

Coordinate spaces:
    ``floor_region_polygon``: normalised [0,1] image space — same space as the
        output ``visibility_polygon``.  NOT floor-plan metres.
    output ``visibility_polygon``: normalised [0,1] floor-plan space — each
        coordinate is divided by the floor-plan real-world dimensions.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
from shapely.geometry import Polygon as ShapelyPolygon

from backend.core.config import settings
from backend.core.logging import get_logger

_log = get_logger(__name__)
_DENSIFY_STEP_PX: int = 10  # floor-region edge densification step (pixels)
_HORIZON_MARGIN_PX: float = 8.0


@dataclasses.dataclass(frozen=True)
class VisibilityResult:
    polygon: list[list[float]] | None
    reason: str | None


def estimate_camera_marker(
    matrix: list[list[float]],
    image_width: int,
    image_height: int,
    floor_plan_width_m: float,
    floor_plan_height_m: float,
    visibility_polygon: list[list[float]] | None,
) -> dict | None:
    if floor_plan_width_m <= 0 or floor_plan_height_m <= 0:
        return None
    h: np.ndarray = np.array(matrix, dtype=np.float64)
    h31, h32, h33 = float(h[2, 0]), float(h[2, 1]), float(h[2, 2])

    def w3(x: float, y: float) -> float:
        return h31 * x + h32 * y + h33

    ref_w3 = w3(image_width / 2.0, float(image_height))
    if abs(ref_w3) < 1e-9:
        return None

    ref_proj = h @ np.array([image_width / 2.0, float(image_height), 1.0], dtype=np.float64)
    ref_m = ref_proj[:2] / ref_proj[2]

    x_norm = float(ref_m[0] / floor_plan_width_m)
    y_norm = float(ref_m[1] / floor_plan_height_m)

    center_w3 = w3(image_width / 2.0, float(image_height) / 2.0)
    sign_ref = 1.0 if ref_w3 > 0 else -1.0

    heading_deg = None
    if center_w3 * sign_ref > 0:
        center_proj = h @ np.array(
            [image_width / 2.0, float(image_height) / 2.0, 1.0], dtype=np.float64
        )
        center_m = center_proj[:2] / center_proj[2]
        cx_norm = float(center_m[0] / floor_plan_width_m)
        cy_norm = float(center_m[1] / floor_plan_height_m)
        dx = cx_norm - x_norm
        dy = cy_norm - y_norm
    elif visibility_polygon and len(visibility_polygon) >= 3:
        poly = ShapelyPolygon(visibility_polygon)
        cx_norm = float(poly.centroid.x)
        cy_norm = float(poly.centroid.y)
        dx = cx_norm - x_norm
        dy = cy_norm - y_norm
    else:
        dx, dy = 0.0, 0.0

    if dx != 0 or dy != 0:
        angle = math.degrees(math.atan2(dx, -dy))
        heading_deg = (angle + 360.0) % 360.0

    return {
        "x_norm": x_norm,
        "y_norm": y_norm,
        "heading_deg": heading_deg,
        "source": "derived",
    }


def floor_side_boundary(
    matrix: list[list[float]],
    image_width: int,
    image_height: int,
    margin_px: float = 8.0,
) -> list[list[float]] | None:
    """Return the image boundary clipped to the floor side of the horizon.

    Returns a polygon of normalised [0, 1] image-space coordinates.
    """
    h31, h32, h33 = matrix[2][0], matrix[2][1], matrix[2][2]

    def w3(x: float, y: float) -> float:
        return h31 * x + h32 * y + h33

    # Reference pixel: bottom-center of the image
    ref_w3 = w3(image_width / 2.0, float(image_height))
    if abs(ref_w3) < 1e-9:
        return None  # Degenerate matrix

    sign_ref = 1.0 if ref_w3 > 0 else -1.0
    grad_norm = math.hypot(h31, h32)
    margin_w3 = margin_px * grad_norm

    def val(x: float, y: float) -> float:
        return w3(x, y) * sign_ref - margin_w3

    # Image corners in pixel space
    W = float(image_width)
    H = float(image_height)
    rect = [
        (0.0, 0.0),
        (W, 0.0),
        (W, H),
        (0.0, H),
    ]

    clipped = []
    for i in range(len(rect)):
        p1 = rect[i]
        p2 = rect[(i + 1) % len(rect)]
        v1 = val(p1[0], p1[1])
        v2 = val(p2[0], p2[1])

        if v1 >= 0:
            clipped.append(p1)

        if (v1 > 0 and v2 < 0) or (v1 < 0 and v2 > 0):
            t = v1 / (v1 - v2)
            ix = p1[0] + t * (p2[0] - p1[0])
            iy = p1[1] + t * (p2[1] - p1[1])
            clipped.append((ix, iy))

    if len(clipped) < 3:
        return None

    # Return as normalised [0, 1] coords
    return [[px / W, py / H] for px, py in clipped]


def _densify_edge(
    p0: list[float],
    p1: list[float],
    image_w: int,
    image_h: int,
) -> list[list[float]]:
    """Return intermediate pixel samples along the normalised edge p0→p1.

    Converts normalised [0,1] endpoints to pixels, densifies to at most one
    sample per ``_DENSIFY_STEP_PX`` pixels, then returns pixel coordinates.
    The endpoint p1 is NOT included (caller appends the next edge's start).
    """
    x0, y0 = p0[0] * image_w, p0[1] * image_h
    x1, y1 = p1[0] * image_w, p1[1] * image_h
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(dist / _DENSIFY_STEP_PX))
    return [[x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps] for i in range(steps)]


def compute_visibility_from_homography(
    matrix: list[list[float]],
    image_width: int,
    image_height: int,
    floor_plan_width_m: float,
    floor_plan_height_m: float,
    floor_region_polygon: list[list[float]] | None = None,
) -> VisibilityResult:
    """Project image boundary (or floor-region polygon) through H to get the visibility polygon.

    Args:
        matrix:
            3x3 homography (pixel -> floor-plan metres), row-major nested list.
        image_width:
            Native pixel width of the camera frame.
        image_height:
            Native pixel height of the camera frame.
        floor_plan_width_m:
            Real-world width of the floor plan in metres.
        floor_plan_height_m:
            Real-world height of the floor plan in metres.
        floor_region_polygon:
            Optional normalised [0,1] image-space polygon tracing the detected
            floor.

    Returns:
        VisibilityResult containing the polygon or a failure reason.
    """
    if floor_plan_width_m <= 0 or floor_plan_height_m <= 0:
        # Expected to be caught by caller, but guard against zero division.
        return VisibilityResult(None, "degenerate_matrix")

    h: np.ndarray = np.array(matrix, dtype=np.float64)

    h31, h32, h33 = float(h[2, 0]), float(h[2, 1]), float(h[2, 2])

    def w3(x: float, y: float) -> float:
        return h31 * x + h32 * y + h33

    ref_w3 = w3(image_width / 2.0, float(image_height))
    if abs(ref_w3) < 1e-9:
        return VisibilityResult(None, "degenerate_matrix")

    sign_ref = 1.0 if ref_w3 > 0 else -1.0

    if floor_region_polygon is not None:
        boundary = []
        n = len(floor_region_polygon)
        for i in range(n):
            p0 = floor_region_polygon[i]
            p1 = floor_region_polygon[(i + 1) % n]
            boundary.extend(_densify_edge(p0, p1, image_width, image_height))
    else:
        _log.warning("visibility_polygon_no_floor_region")
        boundary_norm = floor_side_boundary(matrix, image_width, image_height, _HORIZON_MARGIN_PX)
        if boundary_norm is None:
            return VisibilityResult(None, "no_floor_side")

        boundary = []
        n = len(boundary_norm)
        for i in range(n):
            boundary.extend(
                _densify_edge(
                    boundary_norm[i], boundary_norm[(i + 1) % n], image_width, image_height
                )
            )

    if not boundary:
        return VisibilityResult(None, "no_floor_side")

    # Sign filter
    valid_boundary = []
    for p in boundary:
        if w3(p[0], p[1]) * sign_ref > 0:
            valid_boundary.append(p)

    if len(valid_boundary) < 3:
        return VisibilityResult(None, "no_floor_side")

    src = np.array(valid_boundary, dtype=np.float64)
    ones = np.ones((len(src), 1), dtype=np.float64)
    src_h = np.hstack([src, ones])

    projected = (h @ src_h.T).T
    w3_arr = projected[:, 2:3]
    pts_m = projected[:, :2] / w3_arr

    # Range cap
    max_range = float(settings.get("cts.visibility.max_range_m", 15.0))
    ref_proj = h @ np.array([image_width / 2.0, float(image_height), 1.0], dtype=np.float64)
    ref_m = ref_proj[:2] / ref_proj[2]

    # Pull points exceeding max_range to the cap
    diffs = pts_m - ref_m
    dists = np.linalg.norm(diffs, axis=1)
    over_mask = dists > max_range
    if np.any(over_mask):
        pts_m[over_mask] = ref_m + diffs[over_mask] * (max_range / dists[over_mask, np.newaxis])

    # Convert to normal coordinates
    x_norm = pts_m[:, 0] / floor_plan_width_m
    y_norm = pts_m[:, 1] / floor_plan_height_m

    # Shapely intersection with floor-plan rectangle + 5% buffer
    buf = 0.05
    fp_rect = ShapelyPolygon(
        [(-buf, -buf), (1.0 + buf, -buf), (1.0 + buf, 1.0 + buf), (-buf, 1.0 + buf)]
    )

    pts_norm = np.column_stack((x_norm, y_norm))
    poly = ShapelyPolygon(pts_norm)
    if not poly.is_valid:
        poly = poly.buffer(0)

    intersection = poly.intersection(fp_rect)

    if intersection.is_empty:
        return VisibilityResult(None, "no_floor_side")

    if intersection.geom_type == "MultiPolygon":
        largest_area = -1.0
        best_poly = None
        for p in intersection.geoms:
            if p.area > largest_area:
                largest_area = p.area
                best_poly = p
        intersection = best_poly
    elif intersection.geom_type != "Polygon":
        return VisibilityResult(None, "no_floor_side")

    coords = list(intersection.exterior.coords)
    polygon = [[round(float(x), 4), round(float(y), 4)] for x, y in coords[:-1]]

    return VisibilityResult(polygon, None)
