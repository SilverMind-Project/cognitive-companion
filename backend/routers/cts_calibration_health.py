"""N6: Calibration health endpoint.

Returns per-camera calibration status for the admin health panel.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from prometheus_client import REGISTRY
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.cts_camera import CtsCamera
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("uncalibrated_count_fetch_failed", error=str(exc))
    return 0


@router.get("/calibration/health")
async def calibration_health(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("cts.calibration.view")),
) -> dict:
    """Return per-camera calibration health status."""
    cts_enabled()
    client = getattr(request.app.state, "orchestrator_client", None)

    # Fetch calibration status from orchestrator
    try:
        status = await client.calibration_status() if client is not None else {}
    except Exception:  # noqa: BLE001
        status = {}
    runtime_ids_raw = status.get("homography_camera_ids") if isinstance(status, dict) else None
    runtime_ids = set(runtime_ids_raw) if isinstance(runtime_ids_raw, list) else None

    results: list[dict] = []
    cameras = db.query(CtsCamera).filter(CtsCamera.enabled.is_(True)).order_by(CtsCamera.id).all()
    for cam in cameras:
        camera_id = cam.id
        matrix = cam.homography_matrix
        has_homography = bool(matrix and isinstance(matrix, list) and len(matrix) == 3)
        runtime_has_homography = camera_id in runtime_ids if runtime_ids is not None else None
        residual = cam.homography_residual_m

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
        if has_homography and runtime_has_homography is False:
            severity = "error"
            code = "runtime_matrix_missing"
        elif not has_homography and runtime_has_homography is True:
            severity = "error"
            code = "db_matrix_missing"

        results.append(
            {
                "camera_id": camera_id,
                "homography_present": has_homography,
                "runtime_homography_present": runtime_has_homography,
                "homography_set_at": cam.homography_set_at.isoformat()
                if cam.homography_set_at
                else None,
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
