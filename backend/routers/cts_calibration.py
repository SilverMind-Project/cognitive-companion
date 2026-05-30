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
from datetime import UTC, datetime
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
    CameraVisibilityPolygon,
    HomographyPreviewRequest,
    HomographyPreviewResult,
    HomographyRequest,
    HomographyResult,
    InferredAdjacencyResponse,
    InferredEdgeOut,
    InferredOverlapGroupOut,
    PrivacyZonesRequest,
    VisibilityPolygonsResponse,
)
from backend.services.cts_visibility import compute_visibility_from_homography

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/calibration", tags=["cts-calibration"])


def _has_committed_homography(cam: CtsCamera) -> bool:
    """Return True only for homographies anchored to the shared floor plan."""
    if cam.homography_matrix:
        return True
    if not cam.homography:
        return False
    method = cam.homography.get("method") if isinstance(cam.homography, dict) else None
    return method not in {"depth_auto", "depth_auto_draft"}


def _refresh_visibility_polygon(
    cam: CtsCamera,
    db: Session,
) -> dict:
    """Derive the visibility polygon from the camera's current homography and persist it.

    Called after every homography save (manual or auto).

    Returns a dict with keys:
      - ``computed``: bool — whether the polygon was successfully stored
      - ``point_count``: int — number of polygon vertices (0 if not computed)
      - ``warning``: str | None — human-readable explanation when not computed
    """
    no_op: dict = {"computed": False, "point_count": 0, "warning": None}

    matrix = cam.homography.get("matrix") if cam.homography else cam.homography_matrix
    if not matrix or not cam.snapshot_width or not cam.snapshot_height:
        if not cam.snapshot_width or not cam.snapshot_height:
            no_op["warning"] = (
                "Snapshot dimensions not stored — load a camera snapshot before calibrating."
            )
        else:
            no_op["warning"] = "Homography matrix is missing from stored calibration."
        return no_op

    settings = db.get(HouseholdSettings, 1)
    if not settings:
        no_op["warning"] = "Floor plan settings not configured."
        return no_op

    mpp: float | None = settings.floor_meters_per_pixel
    fp_w_px: int | None = settings.floor_plan_width
    fp_h_px: int | None = settings.floor_plan_height

    if not mpp or not fp_w_px or not fp_h_px:
        no_op["warning"] = (
            "Floor plan scale not set — configure metres/pixel in Floor Plan settings."
        )
        return no_op

    fp_width_m = fp_w_px * mpp
    fp_height_m = fp_h_px * mpp

    polygon = compute_visibility_from_homography(
        matrix=matrix,
        image_width=cam.snapshot_width,
        image_height=cam.snapshot_height,
        floor_plan_width_m=fp_width_m,
        floor_plan_height_m=fp_height_m,
    )

    if polygon is not None:
        cam.visibility_polygon = polygon
        logger.info(
            "cts_visibility_polygon_derived",
            camera_id=cam.id,
            point_count=len(polygon),
        )
        return {"computed": True, "point_count": len(polygon), "warning": None}

    logger.warning(
        "cts_visibility_polygon_degenerate",
        camera_id=cam.id,
        snapshot_dims=f"{cam.snapshot_width}x{cam.snapshot_height}",
        fp_dims_m=f"{fp_width_m:.2f}x{fp_height_m:.2f}",
    )
    return {
        "computed": False,
        "point_count": 0,
        "warning": (
            "Visibility polygon could not be computed — projected points fall far outside "
            "the floor plan. Your calibration point correspondences may be incorrect. "
            "Verify that floor coordinates reference the correct locations on the floor plan."
        ),
    }


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


@router.post("/homography/preview", response_model=HomographyPreviewResult)
async def post_homography_preview(
    body: HomographyPreviewRequest,
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
) -> HomographyPreviewResult:
    """Fit a homography from calibration points and return the result without saving.

    Used by the calibration UI for live preview: called debounced as the operator
    places and adjusts points.
    """
    cts_enabled()
    points_raw = [p.model_dump() for p in body.points]
    try:
        result = await orchestrator.fit_homography(
            camera_id="",  # preview: no camera association
            points=points_raw,
        )
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc

    return HomographyPreviewResult(
        matrix=result["matrix"],
        residuals_m=result["residuals_m"],
        max_residual_m=result["max_residual_m"],
        status=result.get("status", "ok"),
    )


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

    # Server-side validation: reject degenerate or high-error matrices.
    from backend.services.cts.calibration_validator import (
        validate_homography,
    )

    validation = validate_homography(
        matrix=matrix,
        residuals=residuals,
        image_width=body.image_width,
        image_height=body.image_height,
    )
    if not validation.ok:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "calibration_rejected",
                "message": "Homography failed validation",
                "validation": {
                    "ok": validation.ok,
                    "severity": validation.severity,
                    "issues": validation.issues,
                },
            },
        )

    # Persist the computed matrix to the CC database for restart durability.
    cam.homography = {"matrix": matrix}
    cam.homography_residuals = residuals
    cam.snapshot_width = body.image_width
    cam.snapshot_height = body.image_height
    # Populate calibration health columns.
    cam.homography_matrix = matrix
    cam.homography_residual_m = max_residual
    cam.homography_method = "manual"
    cam.homography_set_at = datetime.now(UTC)
    cam.frame_natural_width = body.image_width
    cam.frame_natural_height = body.image_height
    poly_status = _refresh_visibility_polygon(cam, db)
    db.commit()

    logger.info(
        "cts_homography_saved",
        camera_id=body.camera_id,
        snapshot_dims=f"{body.image_width}x{body.image_height}",
        max_residual_m=round(max_residual, 4),
        validation_severity=validation.severity,
        visibility_polygon_computed=poly_status["computed"],
    )

    return HomographyResult(
        camera_id=body.camera_id,
        matrix=matrix,
        residuals_m=residuals,
        max_residual_m=max_residual,
        status=result.get("status", "ok"),
        visibility_polygon_computed=poly_status["computed"],
        visibility_polygon_warning=poly_status.get("warning"),
    )


class AutoCalibrateRequest(BaseModel):
    """Request body for depth-based automatic homography estimation.

    ``minio_key`` is optional.  When omitted the BFF fetches a fresh JPEG
    snapshot from the RTSP ingress and passes it directly to the orchestrator,
    so the button works even when no live tracking stream is running.
    """

    minio_key: str | None = Field(
        default=None,
        min_length=1,
        description="MinIO object key (optional; omit to fetch a live snapshot)",
    )
    fov_deg: float | None = Field(
        default=None,
        ge=20.0,
        le=180.0,
        description=(
            "Camera horizontal FOV in degrees. "
            "Omit to use the value stored on the camera. "
            "Falls back to 70° if neither is set."
        ),
    )


class AutoCalibrateResult(BaseModel):
    """Result returned by the auto-calibrate endpoint."""

    camera_id: str
    draft_matrix: list[list[float]]
    suggested_points: list[dict[str, list[float]]]
    confidence: float
    inlier_count: int
    sample_count: int
    fov_deg: float
    image_width: int
    image_height: int
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

    # Resolution order: request body → stored camera FOV → system default.
    effective_fov = body.fov_deg or cam.horizontal_fov_deg or 70.0

    try:
        result = await orchestrator.auto_calibrate(
            camera_id=camera_id,
            fov_deg=effective_fov,
            minio_key=body.minio_key,
            snapshot_bytes=snapshot_b64,
        )
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc

    # Auto-calibration is draft-only: keep snapshot dimensions for UI context,
    # but never persist the local camera-floor draft as a global homography.
    if result.get("image_width"):
        cam.snapshot_width = int(result["image_width"])
        cam.frame_natural_width = int(result["image_width"])
    if result.get("image_height"):
        cam.snapshot_height = int(result["image_height"])
        cam.frame_natural_height = int(result["image_height"])
    db.commit()

    logger.info(
        "cts_auto_calibration_draft_created",
        camera_id=camera_id,
        effective_fov_deg=effective_fov,
        fov_source=(
            "request"
            if body.fov_deg
            else "camera_stored"
            if cam.horizontal_fov_deg
            else "system_default"
        ),
        confidence=result.get("confidence"),
        inlier_count=result.get("inlier_count"),
        suggested_point_count=len(result.get("suggested_points") or []),
    )

    return AutoCalibrateResult(
        camera_id=camera_id,
        draft_matrix=result["draft_matrix"],
        suggested_points=result.get("suggested_points", []),
        confidence=result["confidence"],
        inlier_count=result["inlier_count"],
        sample_count=result["sample_count"],
        fov_deg=result["fov_deg"],
        image_width=int(result.get("image_width") or cam.snapshot_width or 0),
        image_height=int(result.get("image_height") or cam.snapshot_height or 0),
        method=result.get("method", "depth_auto_draft"),
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
    if not _has_committed_homography(cam):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "cts.calibration.no_homography",
                "message": f"Camera '{camera_id}' has not been calibrated yet.",
            },
        )
    matrix = cam.homography.get("matrix") if cam.homography else cam.homography_matrix
    return {
        "camera_id": camera_id,
        "matrix": matrix,
        "residuals_m": cam.homography_residuals,
    }


# ---------------------------------------------------------------------------
# Visibility polygons endpoints
# ---------------------------------------------------------------------------


@router.get("/visibility_polygons", response_model=VisibilityPolygonsResponse)
def get_visibility_polygons(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
) -> VisibilityPolygonsResponse:
    """Return all enabled cameras with their floor-plan visibility polygons.

    Used by the Coverage tab in CTSFloorPlanView and the adjacency map in
    CTSAdjacencyView.  Cameras without a polygon have ``visibility_polygon=null``.
    """
    from sqlalchemy import select

    cts_enabled()

    cameras = (
        db.execute(
            select(CtsCamera)
            .where(CtsCamera.enabled == True)  # noqa: E712
            .order_by(CtsCamera.id)
        )
        .scalars()
        .all()
    )

    settings = db.get(HouseholdSettings, 1)
    mpp: float | None = settings.floor_meters_per_pixel if settings else None
    fp_w: int | None = settings.floor_plan_width if settings else None
    fp_h: int | None = settings.floor_plan_height if settings else None

    items = [
        CameraVisibilityPolygon(
            camera_id=cam.id,
            camera_name=cam.name,
            has_homography=_has_committed_homography(cam),
            visibility_polygon=cam.visibility_polygon,
        )
        for cam in cameras
    ]

    return VisibilityPolygonsResponse(
        cameras=items,
        floor_meters_per_pixel=mpp,
        floor_plan_width_px=fp_w,
        floor_plan_height_px=fp_h,
    )


@router.post("/visibility_polygons/recompute", status_code=status.HTTP_204_NO_CONTENT)
def post_recompute_visibility_polygons(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
) -> None:
    """Recompute visibility polygons for all calibrated cameras.

    Safe to call at any time — idempotent.  Skips cameras with missing
    snapshot dimensions or unconfigured floor plan scale.
    """
    from sqlalchemy import or_, select

    cts_enabled()
    cameras = (
        db.execute(
            select(CtsCamera).where(
                or_(CtsCamera.homography.is_not(None), CtsCamera.homography_matrix.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    updated = 0
    for cam in cameras:
        if not _has_committed_homography(cam):
            continue
        _refresh_visibility_polygon(cam, db)
        updated += 1
    db.commit()
    logger.info("cts_visibility_polygons_recomputed", camera_count=updated)


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


@router.get("/adjacency/inferred", response_model=InferredAdjacencyResponse)
def get_inferred_adjacency(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.calibrate")),
) -> InferredAdjacencyResponse:
    """Infer adjacency edges from stored visibility polygons (read-only, not persisted).

    The caller decides which edges to adopt by calling ``POST /adjacency``.
    """
    from sqlalchemy import select

    from backend.services.cts_adjacency_inference import infer_adjacency

    cts_enabled()

    cameras = (
        db.execute(
            select(CtsCamera).where(CtsCamera.enabled == True)  # noqa: E712
        )
        .scalars()
        .all()
    )

    cam_dicts = [{"id": c.id, "visibility_polygon": c.visibility_polygon} for c in cameras]
    result = infer_adjacency(cam_dicts)

    return InferredAdjacencyResponse(
        edges=[
            InferredEdgeOut(
                **{"from": e.from_camera, "to": e.to_camera},
                min_transit_s=e.min_transit_s,
                max_transit_s=e.max_transit_s,
                overlap=e.overlap,
                iou=e.iou,
            )
            for e in result.edges
        ],
        overlap_groups=[
            InferredOverlapGroupOut(camera_ids=g.camera_ids, iou=g.iou)
            for g in result.overlap_groups
        ],
        skipped_camera_ids=result.skipped_camera_ids,
    )


# ---------------------------------------------------------------------------
# Adjacency (persisted) endpoints
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
