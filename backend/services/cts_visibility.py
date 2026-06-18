"""Derive camera visibility polygons from homography matrices.

compute_visibility_from_homography:
    Projects boundary points through the homography matrix H (pixel ->
    floor-plan metres) to get the floor-coverage polygon on the floor plan.

    When a ``floor_region_polygon`` (normalised [0,1] image-space polygon
    derived from depth auto-calibration or operator hand-drawing) is provided,
    the boundary is sampled **along the floor-region polygon edges** instead of
    the image border.  This excludes walls that project to meaningless floor
    coordinates.  When absent, falls back to 80 image-border points (original
    behavior) and logs ``visibility_polygon_no_floor_region``.

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

from backend.core.logging import get_logger

_log = get_logger(__name__)
_POINTS_PER_EDGE: int = 20  # 4 edges x 20 = 80 image-border samples (fallback)
_DENSIFY_STEP_PX: int = 10  # floor-region edge densification step (pixels)


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
    import math

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
) -> list[list[float]] | None:
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
            floor (same space as the output, NOT floor metres).  When provided,
            boundary points are sampled along its edges instead of the image
            border, excluding walls.  When ``None`` the original 80-point
            image-border behavior is used and a warning is logged.

    Returns:
        A list of normalised ``[x_norm, y_norm]`` polygon vertices in floor-plan
        space.  Returns ``None`` if:
        - floor plan dimensions are zero or negative
        - the matrix is degenerate (w3 near-zero for any boundary point)
        - any projected point falls further than 1.5 units outside [0, 1]
          (indicates a miscalibrated or inverted matrix)
    """
    import numpy as np

    if floor_plan_width_m <= 0 or floor_plan_height_m <= 0:
        return None

    h: np.ndarray = np.array(matrix, dtype=np.float64)

    W = float(image_width)
    H = float(image_height)

    if floor_region_polygon is not None:
        # Sample along the floor-region polygon edges (densified for lens distortion).
        boundary: list[list[float]] = []
        n = len(floor_region_polygon)
        for i in range(n):
            p0 = floor_region_polygon[i]
            p1 = floor_region_polygon[(i + 1) % n]
            boundary.extend(_densify_edge(p0, p1, image_width, image_height))
    else:
        # Fallback: original 80-point image-border sampling.
        _log.warning("visibility_polygon_no_floor_region")
        n_pts = _POINTS_PER_EDGE
        boundary = []
        for i in range(n_pts):
            t = i / n_pts
            boundary.append([W * t, 0.0])
        for i in range(n_pts):
            t = i / n_pts
            boundary.append([W, H * t])
        for i in range(n_pts):
            t = i / n_pts
            boundary.append([W * (1 - t), H])
        for i in range(n_pts):
            t = i / n_pts
            boundary.append([0.0, H * (1 - t)])

    if not boundary:
        return None

    src = np.array(boundary, dtype=np.float64)

    ones = np.ones((len(src), 1), dtype=np.float64)
    src_h = np.hstack([src, ones])

    projected = (h @ src_h.T).T

    w3 = projected[:, 2:3]
    if np.any(np.abs(w3) < 1e-9):
        return None

    pts_m = projected[:, :2] / w3

    x_norm = pts_m[:, 0] / floor_plan_width_m
    y_norm = pts_m[:, 1] / floor_plan_height_m

    if np.any(x_norm < -1.5) or np.any(x_norm > 2.5):
        return None
    if np.any(y_norm < -1.5) or np.any(y_norm > 2.5):
        return None

    polygon = [
        [round(float(x), 4), round(float(y), 4)]
        for x, y in zip(x_norm.tolist(), y_norm.tolist(), strict=True)
    ]
    return polygon
