"""CTS diagnostics endpoints: calibration health."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.cts_camera import CtsCamera
from backend.routers.cts_deps import cts_enabled
from backend.schemas.calibration import (
    CalibrationDiagnosticsEntry,
    CalibrationDiagnosticsResponse,
    CalibrationValidation,
)

router = APIRouter(prefix="/cts/diagnostics", tags=["cts-diagnostics"])

logger = get_logger(__name__)


@router.get("/calibration", response_model=CalibrationDiagnosticsResponse)
async def get_calibration_diagnostics(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> CalibrationDiagnosticsResponse:
    """Return per-camera calibration health for the calibration health panel."""
    cts_enabled()

    cameras = list(db.scalars(select(CtsCamera).where(CtsCamera.enabled.is_(True))))

    entries: list[CalibrationDiagnosticsEntry] = []
    for cam in cameras:
        validation = None
        if cam.homography_matrix is not None:
            from backend.services.cts.calibration_validator import validate_homography

            result = validate_homography(
                matrix=cam.homography_matrix,
                residuals=cam.homography_residuals,
                image_width=cam.snapshot_width or 0,
                image_height=cam.snapshot_height or 0,
            )
            validation = CalibrationValidation(
                ok=result.ok,
                severity=result.severity,
                issues=result.issues,
                metrics=result.metrics,
            )

        entries.append(
            CalibrationDiagnosticsEntry(
                camera_id=cam.id,
                room_id=str(cam.room_id) if cam.room_id else None,
                room_name=cam.room_name,
                has_homography=cam.homography_matrix is not None,
                homography_set_at=(
                    cam.homography_set_at.isoformat() if cam.homography_set_at else None
                ),
                homography_method=cam.homography_method,
                validation=validation,
            )
        )

    return CalibrationDiagnosticsResponse(cameras=entries)
