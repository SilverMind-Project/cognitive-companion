"""Derive camera visibility polygons from homography matrices.

compute_visibility_from_homography:
    Projects 80 densely sampled boundary points from the camera image through
    the homography matrix H (pixel -> floor-plan metres) to get the actual
    coverage polygon on the floor plan.

    Instead of projecting only the 4 image corners, we sample 20 points along
    each of the 4 image edges (top, right, bottom, left) for a total of 80
    boundary points.  This captures the non-linear distortion of wide-angle
    lenses more accurately than a 4-point projection.

    All returned coordinates are normalised to [0, 1] relative to the floor-plan
    image dimensions so the polygon is independent of floor-plan image resolution.
"""

from __future__ import annotations

_POINTS_PER_EDGE: int = 20  # 4 edges x 20 points = 80 boundary samples


def compute_visibility_from_homography(
    matrix: list[list[float]],
    image_width: int,
    image_height: int,
    floor_plan_width_m: float,
    floor_plan_height_m: float,
) -> list[list[float]] | None:
    """Project image boundary through H to get the floor-plan visibility polygon.

    Args:
        matrix:
            3x3 homography (pixel -> floor-plan metres), row-major nested list.
            This is the matrix stored in ``cts_cameras.homography["matrix"]``.
        image_width:
            Native pixel width of the camera frame (``cts_cameras.snapshot_width``).
        image_height:
            Native pixel height of the camera frame (``cts_cameras.snapshot_height``).
        floor_plan_width_m:
            Real-world width of the floor plan in metres.
        floor_plan_height_m:
            Real-world height of the floor plan in metres.

    Returns:
        A list of 80 normalised ``[x_norm, y_norm]`` polygon vertices, where
        ``x_norm = floor_x_m / floor_plan_width_m`` and similarly for y.
        Returns ``None`` if:
        - floor plan dimensions are zero or negative
        - the matrix is degenerate (w3 near-zero for any boundary point)
        - any projected point falls further than 1.5 units outside [0, 1]
          (indicates a miscalibrated or inverted matrix)
    """
    import numpy as np

    if floor_plan_width_m <= 0 or floor_plan_height_m <= 0:
        return None

    h: np.ndarray = np.array(matrix, dtype=np.float64)  # (3, 3)

    W = float(image_width)
    H = float(image_height)
    n = _POINTS_PER_EDGE

    # Build boundary sample list, ordered to preserve polygon winding:
    # top (left->right), right (top->bottom), bottom (right->left), left (bottom->top).
    # The endpoint of each edge is NOT included to avoid duplicating corner points.
    boundary: list[list[float]] = []
    for i in range(n):
        t = i / n
        boundary.append([W * t, 0.0])
    for i in range(n):
        t = i / n
        boundary.append([W, H * t])
    for i in range(n):
        t = i / n
        boundary.append([W * (1 - t), H])
    for i in range(n):
        t = i / n
        boundary.append([0.0, H * (1 - t)])

    src = np.array(boundary, dtype=np.float64)  # (80, 2)

    # Homogeneous coordinates: append ones.
    ones = np.ones((len(src), 1), dtype=np.float64)
    src_h = np.hstack([src, ones])  # (80, 3)

    projected = (h @ src_h.T).T  # (80, 3)

    # De-homogenise.
    w3 = projected[:, 2:3]  # (80, 1)
    if np.any(np.abs(w3) < 1e-9):
        return None

    pts_m = projected[:, :2] / w3  # (80, 2)

    # Normalise to [0, 1] relative to floor-plan real-world dimensions.
    x_norm = pts_m[:, 0] / floor_plan_width_m
    y_norm = pts_m[:, 1] / floor_plan_height_m

    # Sanity check: reject if any point projects far outside the floor plan.
    if np.any(x_norm < -1.5) or np.any(x_norm > 2.5):
        return None
    if np.any(y_norm < -1.5) or np.any(y_norm > 2.5):
        return None

    # Round to 4 decimal places to keep the stored JSON compact.
    polygon = [
        [round(float(x), 4), round(float(y), 4)]
        for x, y in zip(x_norm.tolist(), y_norm.tolist(), strict=True)
    ]
    return polygon
