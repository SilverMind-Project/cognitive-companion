"""N6: Calibration health endpoint.

Returns per-camera calibration status for the admin health panel.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from prometheus_client import REGISTRY

from backend.core.auth import require_permission
from backend.core.logging import get_logger
from backend.routers.cts_deps import cts_enabled

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-calibration-health"])


def _get_uncalibrated_detection_count() -> int:
    """Read cumulative uncalibrated detection count from Prometheus registry.

    This is a process-lifetime counter, not a rolling 24-hour window.
    """
    try:
        for metric in REGISTRY.collect():
            if metric.name == "cts_uncalibrated_detections_total":
                return int(sum(sample.value for sample in metric.samples))
    except Exception as exc:
        logger.warning("uncalibrated_count_fetch_failed", error=str(exc))
    return 0


@router.get("/calibration/health")
async def calibration_health(
    request: Request,
    _auth=Depends(require_permission("cts.calibration.view")),
) -> dict:
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
            }
        )

    uncalibrated_count = _get_uncalibrated_detection_count()

    return {
        "cameras": results,
        "uncalibrated_detection_count": uncalibrated_count,
        "uncalibrated_count_is_cumulative": True,
        "generated_at": datetime.now(UTC).isoformat(),
    }
