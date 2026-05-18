"""CTS calibration endpoints: homography, privacy zones, and camera adjacency.

Homography computation runs in the tracking orchestrator (``continuous-tracking``),
which is the authoritative spatial-processing service.  This BFF router is a thin
proxy: it validates camera existence, persists the computed matrix to the CC
database (for restart durability), and forwards errors from the orchestrator.

Routes:
    POST /api/v1/cts/calibration/homography
    GET  /api/v1/cts/calibration/homography/{camera_id}
    POST /api/v1/cts/calibration/auto/{camera_id}
    POST /api/v1/cts/calibration/privacy_zones
    GET  /api/v1/cts/calibration/privacy_zones/{camera_id}
    POST /api/v1/cts/calibration/adjacency
    GET  /api/v1/cts/calibration/adjacency
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from backend.integrations.ingress_admin_client import IngressAdminClient
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.cts_camera import CtsCamera
from backend.models.household_settings import HouseholdSettings
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_ingress_admin_client, get_orchestrator_client
from backend.schemas.cts_camera import (
    AdjacencyRequest,
    HomographyRequest,
    HomographyResult,
    PrivacyZonesRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/calibration", tags=["cts-calibration"])


def _upstream_to_http(exc: UpstreamError) -> HTTPException:
    import json

    code_map = {503: status.HTTP_503_SERVICE_UNAVAILABLE, 504: status.HTTP_504_GATEWAY_TIMEOUT}
    http_code = code_map.get(exc.status, status.HTTP_502_BAD_GATEWAY)
    # Try to forward the upstream's own error detail (code + message) so the UI
    # shows an actionable description rather than the generic "upstream.unknown".
    upstream_code = str(exc.code)
    message = str(exc)
    if exc.body:
        try:
            parsed = json.loads(exc.body)
            detail = parsed.get("detail", parsed)
            if isinstance(detail, dict):
                upstream_code = detail.get("code", upstream_code)
                message = detail.get("message", message)
        except (ValueError, AttributeError):
            pass
    return HTTPException(
        status_code=http_code,
        detail={"code": upstream_code, "service": exc.service, "message": message},
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
    """Fit a homography from calibration points and persist it.

    Delegates computation to the tracking orchestrator (``POST
    /internal/calibration/homography/fit``), which runs OpenCV RANSAC
    server-side.  Returns 400 when the maximum per-point reprojection
    error exceeds 0.5 m.
    """
    cts_enabled()

    cam = db.get(CtsCamera, body.camera_id)
    if not cam:
        raise NotFoundError("Camera", body.camera_id)

    points_raw = [p.model_dump() for p in body.points]

    try:
        result = await orchestrator.fit_homography(
            camera_id=body.camera_id,
            points=points_raw,
        )
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc

    matrix: list[list[float]] = result["matrix"]
    residuals: list[float] = result["residuals_m"]
    max_residual: float = result["max_residual_m"]

    # Persist the computed matrix to the CC database for restart durability.
    cam.homography = {"matrix": matrix}
    cam.homography_residuals = residuals
    db.commit()

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
        status=result.get("status", "ok"),
    )


class AutoCalibrateRequest(BaseModel):
    """Request body for depth-based automatic homography estimation.

    ``minio_key`` is optional.  When omitted the BFF fetches a fresh JPEG
    snapshot from the RTSP ingress and passes it directly to the orchestrator,
    so the button works even when no live tracking stream is running.
    """

    minio_key: str | None = Field(
        default=None, min_length=1, description="MinIO object key (optional; omit to fetch a live snapshot)"
    )
    fov_deg: float = Field(
        default=70.0,
        ge=20.0,
        le=180.0,
        description="Camera horizontal field of view in degrees (default 70°, typical surveillance).",
    )


class AutoCalibrateResult(BaseModel):
    """Result returned by the auto-calibrate endpoint."""

    camera_id: str
    matrix: list[list[float]]
    confidence: float
    inlier_count: int
    sample_count: int
    fov_deg: float
    method: str
    warning: str | None = None


@router.post("/auto/{camera_id}", response_model=AutoCalibrateResult)
async def post_auto_calibrate(
    camera_id: str,
    body: AutoCalibrateRequest,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
    ingress: IngressAdminClient = Depends(get_ingress_admin_client),
) -> AutoCalibrateResult:
    """Estimate a homography automatically using monocular depth estimation.

    When *minio_key* is omitted the BFF fetches a fresh JPEG from the RTSP
    ingress and passes it to the orchestrator as base64, so the button is
    usable immediately after loading a camera snapshot without waiting for a
    live tracking stream to supply the key.

    Returns 503 when the depth model is unavailable in Triton.
    Returns 409 when no reliable floor plane can be detected.
    """
    cts_enabled()

    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)

    snapshot_b64: str | None = None
    if body.minio_key is None:
        try:
            jpeg_bytes = await ingress.snapshot(camera_id=camera_id)
            snapshot_b64 = base64.b64encode(jpeg_bytes).decode()
        except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
            raise _upstream_to_http(exc) from exc

    try:
        result = await orchestrator.auto_calibrate(
            camera_id=camera_id,
            fov_deg=body.fov_deg,
            minio_key=body.minio_key,
            snapshot_bytes=snapshot_b64,
        )
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc

    matrix: list[list[float]] = result["matrix"]

    # Persist the auto-computed matrix to the CC database so it survives
    # an orchestrator restart.  We store no residuals (they're not meaningful
    # for the depth-based method) and mark the method in the JSON blob.
    cam.homography = {"matrix": matrix, "method": "depth_auto"}
    cam.homography_residuals = None
    db.commit()

    logger.info(
        "cts_auto_calibration_saved",
        camera_id=camera_id,
        confidence=result.get("confidence"),
        inlier_count=result.get("inlier_count"),
    )

    return AutoCalibrateResult(
        camera_id=camera_id,
        matrix=matrix,
        confidence=result["confidence"],
        inlier_count=result["inlier_count"],
        sample_count=result["sample_count"],
        fov_deg=result["fov_deg"],
        method=result.get("method", "depth_auto"),
        warning=result.get("warning"),
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


def _get_or_create_settings(db: Session) -> HouseholdSettings:
    """Return the singleton HouseholdSettings row, creating it if absent."""
    from sqlalchemy.exc import IntegrityError

    row = db.get(HouseholdSettings, 1)
    if row is not None:
        return row
    row = HouseholdSettings(id=1)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        row = db.get(HouseholdSettings, 1)
        if row is None:
            raise
    return row


@router.post("/adjacency", status_code=status.HTTP_204_NO_CONTENT)
async def post_adjacency(
    body: AdjacencyRequest,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
) -> None:
    """Replace the full camera adjacency graph, persist to DB, and push to the orchestrator."""
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

    # Persist to DB using from/to alias keys so the orchestrator startup loader
    # can send them back unchanged.
    edges_data = [e.model_dump(by_alias=True) for e in body.edges]
    settings_row = _get_or_create_settings(db)
    settings_row.cts_adjacency_edges = edges_data
    db.commit()

    # Push live update to orchestrator (non-fatal if unreachable).
    try:
        await orchestrator.post_adjacency(edges=edges_data)
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        logger.warning("cts_adjacency_push_failed", error=str(exc))

    logger.info("cts_adjacency_saved", edge_count=len(edges_data))


@router.get("/adjacency")
def get_adjacency(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
) -> dict:
    """Return the persisted adjacency graph from the database."""
    cts_enabled()
    row = db.get(HouseholdSettings, 1)
    edges = (row.cts_adjacency_edges or []) if row is not None else []
    return {"edge_count": len(edges), "edges": edges}
