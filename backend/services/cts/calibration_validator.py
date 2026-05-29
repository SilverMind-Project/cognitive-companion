"""Server-side calibration validator.

Shared between cognitive-companion (authoritative, validates on save)
and tracking-orchestrator (defensive, refuses bad homographies during sync).
Both must produce identical results.

The validator is a pure module: no I/O, no DB, no HTTP. All inputs are
passed in; all outputs are deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class HomographyValidation:
    ok: bool
    severity: str  # "ok" | "warning" | "error"
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def validate_homography(
    matrix: list[list[float]],
    residuals: list[float] | None = None,
    floor_plan_mpp: float | None = None,
    camera_room_polygon: list[tuple[float, float]] | None = None,
    image_width: int = 0,
    image_height: int = 0,
) -> HomographyValidation:
    """Sanity checks beyond raw residuals.

    Args:
        matrix: 3x3 homography matrix, row-major.
        residuals: per-point reprojection residuals in metres.
        floor_plan_mpp: metres-per-pixel of the floor plan (for polygon check).
        camera_room_polygon: vertices of the claimed room's floor polygon.
        image_width, image_height: pixel dimensions of the camera frame.

    Returns:
        HomographyValidation with ok/severity/issues/metrics.
    """
    issues: list[str] = []
    metrics: dict[str, float] = {}

    # 1. Residual check.
    if residuals:
        max_res = max(residuals)
        metrics["max_residual_m"] = max_res
        if max_res > 0.5:
            issues.append(f"max residual {max_res:.2f} m exceeds 0.5 m threshold")
        elif max_res > 0.25:
            issues.append(f"max residual {max_res:.2f} m exceeds warning threshold")
        if residuals:
            metrics["mean_residual_m"] = sum(residuals) / len(residuals)
    else:
        metrics["max_residual_m"] = 0.0
        metrics["mean_residual_m"] = 0.0

    # 2. Determinant sanity: near-zero det means degenerate matrix.
    m = np.array(matrix, dtype=np.float64)
    if m.shape == (3, 3):
        det = float(np.linalg.det(m))
        metrics["determinant"] = det
        if abs(det) < 1e-6:
            issues.append("matrix determinant near zero (degenerate)")

    # 3. Polygon containment check: project image corners and verify at
    #    least one lands inside the claimed room's floor polygon.
    if (
        camera_room_polygon is not None
        and floor_plan_mpp is not None
        and image_width > 0
        and image_height > 0
        and m.shape == (3, 3)
    ):
        from shapely.geometry import Point as ShapelyPoint
        from shapely.geometry import Polygon as ShapelyPolygon

        room_poly = ShapelyPolygon(camera_room_polygon)
        corners_px = [
            (0, 0),
            (image_width, 0),
            (image_width, image_height),
            (0, image_height),
        ]
        projected = [_project_point(m, px, py, floor_plan_mpp) for px, py in corners_px]
        any_inside = any(room_poly.contains(ShapelyPoint(px, py)) for px, py in projected)
        if not any_inside:
            issues.append(
                "projected frame corners fall outside claimed room polygon; "
                "camera→room binding may be wrong"
            )

    # 4. Severity classification.
    is_error = any("exceeds 0.5" in i or "degenerate" in i for i in issues)
    severity = "error" if is_error else ("warning" if issues else "ok")

    return HomographyValidation(
        ok=(severity != "error"),
        severity=severity,
        issues=list(issues),
        metrics=metrics,
    )


def _project_point(
    matrix: np.ndarray,
    px: float,
    py: float,
    mpp: float,
) -> tuple[float, float]:
    """Project a pixel point through the homography to floor-plan metres."""
    p = np.array([px, py, 1.0], dtype=np.float64)
    projected = matrix @ p
    if abs(projected[2]) < 1e-8:
        return (0.0, 0.0)
    projected /= projected[2]
    return (float(projected[0] * mpp), float(projected[1] * mpp))
