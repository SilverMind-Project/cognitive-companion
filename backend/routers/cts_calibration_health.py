"""N6: Calibration health endpoint.

Returns per-camera calibration status for the admin health panel.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from backend.core.logging import get_logger

from backend.core.auth import require_permission
from backend.routers.cts_deps import cts_enabled

logger = get_logger(__name__)

router = APIRouter(tags=["cts-calibration-health"])


@router.get("/calibration/health")
async def calibration_health(
    request: Request,
    _auth=Depends(require_permission("cts.cameras.read")),
) -> list[dict]:
    """Return per-camera calibration health status."""
    cts_enabled()
    client = getattr(request.app.state, "orchestrator_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail={"code": "cts.upstream_unavailable"})

    try:
        cameras_raw = await client._request("GET", "/api/v1/cts/cameras?include_calibration=true")
        cameras = cameras_raw.json()
        if not isinstance(cameras, list):
            cameras = [cameras]
    except Exception:
        logger.exception("calibration_health_fetch_failed")
        cameras = []

    # Fetch calibration status from orchestrator
    try:
        status_raw = await client._request("GET", "/internal/calibration/status")
        status = status_raw.json()
    except Exception:
        status = {}

    results: list[dict] = []
    for cam in cameras:
        if not isinstance(cam, dict):
            continue
        camera_id = cam.get("id", "")
        matrix = cam.get("homography_matrix")
        has_homography = bool(matrix and isinstance(matrix, list) and len(matrix) == 3)
        residual = cam.get("homography_residual_m")
        status_entry = status.get(camera_id, {})

        severity = "ok"
        code = None
        if has_homography and residual is not None:
            r = float(residual)
            if r > 0.5:
                severity = "error"
                code = "high_residual"
            elif r > 0.25:
                severity = "warning"
                code = "elevated_residual"
        elif not has_homography and status_entry.get("calibrated"):
            severity = "error"
            code = "matrix_missing"

        results.append(
            {
                "camera_id": camera_id,
                "homography_present": has_homography,
                "last_validated_at": status_entry.get("last_validated_at"),
                "severity": severity,
                "code": code,
                "residual_m": float(residual) if residual is not None else None,
                "uncalibrated_detection_count_24h": 0,
            }
        )

    return results
