"""CTS calibration endpoints: homography, privacy zones, and camera adjacency.

Homography is computed with OpenCV's ``findHomography`` (RANSAC method).
Residuals are validated server-side; the API returns 400 when the maximum
per-point reprojection error exceeds 0.5 m (§5.20 gate 8).

Routes:
    POST /api/v1/cts/calibration/homography
    GET  /api/v1/cts/calibration/homography/{camera_id}
    POST /api/v1/cts/calibration/privacy_zones
    GET  /api/v1/cts/calibration/privacy_zones/{camera_id}
    POST /api/v1/cts/calibration/adjacency
    GET  /api/v1/cts/calibration/adjacency
"""

from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.cts_camera import CtsCamera
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_orchestrator_client
from backend.schemas.cts_camera import (
    AdjacencyRequest,
    HomographyRequest,
    HomographyResult,
    PrivacyZonesRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/calibration", tags=["cts-calibration"])

# Validation thresholds (metres)
_RESIDUAL_ERROR = 0.5
_RESIDUAL_WARN = 0.25


# ---------------------------------------------------------------------------
# Homography math (pure function: unit-testable without FastAPI)
# ---------------------------------------------------------------------------


def compute_homography(
    pixel_points: list[list[float]],
    floor_points: list[list[float]],
) -> tuple[list[list[float]], list[float]]:
    """Fit a 3x3 homography and return (matrix, per-point residuals in metres).

    Uses OpenCV ``findHomography`` with the RANSAC method for robustness
    against outliers.  Each residual is the Euclidean distance (in metres)
    between the back-projected point and the provided floor point.

    Raises ``ImportError`` if ``opencv-python-headless`` is not installed.
    Raises ``ValueError`` if fewer than 4 point pairs are provided.
    """
    import cv2

    if len(pixel_points) < 4 or len(floor_points) < 4:
        raise ValueError("At least 4 point pairs required to fit a homography")

    src = np.array(pixel_points, dtype=np.float64)
    dst = np.array(floor_points, dtype=np.float64)

    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, ransacReprojThreshold=5.0)
    if H is None:
        raise ValueError("findHomography did not converge: check that points are not collinear")

    # Compute per-point reprojection error in floor-plan metres.
    ones = np.ones((len(src), 1), dtype=np.float64)
    src_h = np.hstack([src, ones])  # (N, 3)
    proj_h = (H @ src_h.T).T  # (N, 3)
    proj = proj_h[:, :2] / proj_h[:, 2:3]  # normalise homogeneous coords

    residuals: list[float] = [
        float(np.linalg.norm(proj[i] - dst[i])) for i in range(len(src))
    ]

    matrix: list[list[float]] = H.tolist()
    return matrix, residuals


def _residual_status(max_residual: float) -> str:
    if max_residual <= _RESIDUAL_WARN:
        return "ok"
    if max_residual <= _RESIDUAL_ERROR:
        return "warning"
    return "error"


def _upstream_to_http(exc: UpstreamError) -> HTTPException:
    code_map = {503: status.HTTP_503_SERVICE_UNAVAILABLE, 504: status.HTTP_504_GATEWAY_TIMEOUT}
    http_code = code_map.get(exc.status, status.HTTP_502_BAD_GATEWAY)
    return HTTPException(
        status_code=http_code,
        detail={"code": str(exc.code), "service": exc.service, "message": str(exc)},
    )


# ---------------------------------------------------------------------------
# Homography endpoints
# ---------------------------------------------------------------------------


@router.post("/homography", response_model=HomographyResult)
async def post_homography(
    body: HomographyRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
) -> HomographyResult:
    """Fit a homography from calibration points, validate residuals, and push to orchestrator.

    Returns 400 with ``error.code = "cts.calibration.residuals_too_high"``
    when the maximum per-point error exceeds 0.5 m (§5.20 gate 8).
    """
    cts_enabled()

    cam = db.get(CtsCamera, body.camera_id)
    if not cam:
        raise NotFoundError("Camera", body.camera_id)

    pixel_pts = [p.pixel for p in body.points]
    floor_pts = [p.floor_m for p in body.points]

    try:
        matrix, residuals = compute_homography(pixel_pts, floor_pts)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "cts.calibration.opencv_missing",
                "message": "opencv-python-headless is not installed on this server.",
            },
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "cts.calibration.invalid_points", "message": str(exc)},
        ) from exc

    max_residual = max(residuals)

    if max_residual > _RESIDUAL_ERROR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "cts.calibration.residuals_too_high",
                "message": (
                    f"Maximum reprojection error {max_residual:.3f} m exceeds "
                    f"the {_RESIDUAL_ERROR} m threshold. Adjust calibration points."
                ),
                "max_residual_m": max_residual,
                "residuals_m": residuals,
            },
        )

    # Persist to camera row.
    cam.homography = {"matrix": matrix}
    cam.homography_residuals = residuals
    db.commit()

    # Push to orchestrator (non-fatal if orchestrator is unreachable).
    try:
        await orchestrator.post_homography(
            camera_id=body.camera_id,
            matrix=matrix,
            points=[p.model_dump() for p in body.points],
            meta={"max_residual_m": max_residual},
        )
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        logger.warning(
            "cts_homography_push_failed",
            camera_id=body.camera_id,
            error=str(exc),
        )

    logger.info(
        "cts_homography_saved",
        camera_id=body.camera_id,
        max_residual_m=round(max_residual, 4),
    )

    return HomographyResult(
        camera_id=body.camera_id,
        matrix=matrix,
        residuals_m=residuals,
        max_residual_m=max_residual,
        status=_residual_status(max_residual),
    )


@router.get("/homography/{camera_id}")
def get_homography(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
) -> dict:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    if not cam.homography:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cts.calibration.no_homography",
                    "message": f"Camera '{camera_id}' has not been calibrated yet."},
        )
    return {
        "camera_id": camera_id,
        "matrix": cam.homography.get("matrix"),
        "residuals_m": cam.homography_residuals,
    }


# ---------------------------------------------------------------------------
# Privacy zones endpoints
# ---------------------------------------------------------------------------


@router.post("/privacy_zones", status_code=status.HTTP_204_NO_CONTENT)
async def post_privacy_zones(
    body: PrivacyZonesRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
) -> None:
    """Replace all privacy zones for a camera and push to the orchestrator."""
    cts_enabled()
    cam = db.get(CtsCamera, body.camera_id)
    if not cam:
        raise NotFoundError("Camera", body.camera_id)

    zones_data: list[dict[str, Any]] = [z.model_dump() for z in body.zones]
    cam.privacy_zones = zones_data
    db.commit()

    try:
        await orchestrator.post_privacy_zones(
            camera_id=body.camera_id,
            zones=zones_data,
        )
        # Trigger a hot-reload so the orchestrator picks up the change.
        await orchestrator.post_reload()
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        logger.warning(
            "cts_privacy_zones_push_failed",
            camera_id=body.camera_id,
            error=str(exc),
        )

    logger.info(
        "cts_privacy_zones_saved",
        camera_id=body.camera_id,
        zone_count=len(zones_data),
    )


@router.get("/privacy_zones/{camera_id}")
def get_privacy_zones(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
) -> dict:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    return {"camera_id": camera_id, "zones": cam.privacy_zones or []}


# ---------------------------------------------------------------------------
# Adjacency endpoints
# ---------------------------------------------------------------------------


@router.post("/adjacency", status_code=status.HTTP_204_NO_CONTENT)
async def post_adjacency(
    body: AdjacencyRequest,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
) -> None:
    """Replace the full camera adjacency graph and push to the orchestrator."""
    cts_enabled()

    for edge in body.edges:
        if edge.max_transit_s < edge.min_transit_s:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "cts.calibration.invalid_transit",
                    "message": (
                        f"Edge {edge.from_camera}->{edge.to_camera}: "
                        "max_transit_s must be >= min_transit_s"
                    ),
                },
            )

    edges_data = [e.model_dump(by_alias=False) for e in body.edges]

    try:
        await orchestrator.post_adjacency(edges=edges_data)
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc

    logger.info("cts_adjacency_saved", edge_count=len(edges_data))


@router.get("/adjacency")
async def get_adjacency(
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Fetch the current adjacency state from the orchestrator."""
    cts_enabled()
    try:
        status_data = await orchestrator.calibration_status()
        return {"edge_count": status_data.get("adjacency_edge_count", 0)}
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc
