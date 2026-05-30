"""CTS camera CRUD, health, and snapshot endpoints.

All write paths (POST, PATCH, DELETE) require ``cts.cameras.write``.
Read paths (GET, test-connect, snapshot) require ``cts.cameras.read``.

When ``cts.enabled=false`` every handler returns 404 with code
``cts.disabled`` so no CTS code runs.

Routes:
    GET    /api/v1/cts/cameras
    POST   /api/v1/cts/cameras
    GET    /api/v1/cts/cameras/{camera_id}
    PATCH  /api/v1/cts/cameras/{camera_id}
    DELETE /api/v1/cts/cameras/{camera_id}
    POST   /api/v1/cts/cameras/test-connect
    GET    /api/v1/cts/cameras/{camera_id}/snapshot
    GET    /api/v1/cts/cameras/{camera_id}/health
    POST   /api/v1/cts/cameras/{camera_id}/reload
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from backend.integrations.ingress_admin_client import IngressAdminClient
from backend.models.cts_camera import CtsCamera
from backend.models.room import Room
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_ingress_admin_client
from backend.schemas.cts_camera import CtsCameraCreate, CtsCameraOut, CtsCameraUpdate, RoomRef

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/cameras", tags=["cts-cameras"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upstream_to_http(exc: UpstreamError) -> HTTPException:
    code_map = {
        400: status.HTTP_400_BAD_REQUEST,
        403: status.HTTP_403_FORBIDDEN,
        404: status.HTTP_404_NOT_FOUND,
        409: status.HTTP_409_CONFLICT,
        503: status.HTTP_503_SERVICE_UNAVAILABLE,
        504: status.HTTP_504_GATEWAY_TIMEOUT,
    }
    http_code = code_map.get(exc.status, status.HTTP_502_BAD_GATEWAY)
    return HTTPException(
        status_code=http_code,
        detail={"code": str(exc.code), "service": exc.service, "message": str(exc)},
    )


def _resolve_room(db: Session, room_id: int | None) -> RoomRef | None:
    """Resolve a room_id to a RoomRef for API output."""
    if room_id is None:
        return None
    room = db.get(Room, room_id)
    if room is None:
        return None
    return RoomRef(id=room.id, name=room.name)


def _denormalise_room_name(db: Session, room_id: int) -> str:
    """Return the Room name for a room_id, raising when the room is invalid."""
    room = db.get(Room, room_id)
    if room is None:
        raise NotFoundError("Room", room_id)
    return room.name


def _has_committed_homography(cam: CtsCamera) -> bool:
    if cam.homography_matrix:
        return True
    if not cam.homography:
        return False
    method = cam.homography.get("method") if isinstance(cam.homography, dict) else None
    return method not in {"depth_auto", "depth_auto_draft"}


def _to_out(cam: CtsCamera, db: Session | None = None) -> CtsCameraOut:
    residuals = cam.homography_residuals
    room = None
    if db is not None and cam.room_id is not None:
        room = _resolve_room(db, cam.room_id)
    return CtsCameraOut(
        id=cam.id,
        name=cam.name,
        rtsp_url=cam.rtsp_url,
        room_name=cam.room_name or "",
        room_id=cam.room_id,
        enabled=cam.enabled,
        floor_plan_key=cam.floor_plan_key,
        rotation_degrees=cam.rotation_degrees,
        face_id_enabled=cam.face_id_enabled if cam.face_id_enabled is not None else True,
        face_id_min_confidence=cam.face_id_min_confidence,
        role=cam.role,
        horizontal_fov_deg=cam.horizontal_fov_deg,
        mounting_height_m=cam.mounting_height_m,
        tilt_deg=cam.tilt_deg,
        room=room,
        has_homography=_has_committed_homography(cam),
        homography_residuals=residuals if residuals else None,
        privacy_zone_count=len(cam.privacy_zones) if cam.privacy_zones else 0,
        health=cam.health_json,
        snapshot_width=cam.snapshot_width,
        snapshot_height=cam.snapshot_height,
        visibility_polygon=cam.visibility_polygon,
        created_at=cam.created_at,
        updated_at=cam.updated_at,
    )


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CtsCameraOut])
def list_cameras(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> list[CtsCameraOut]:
    cts_enabled()
    return [_to_out(c, db) for c in db.query(CtsCamera).order_by(CtsCamera.name).all()]


@router.post("", response_model=CtsCameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CtsCameraCreate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
) -> CtsCameraOut:
    cts_enabled()
    if db.get(CtsCamera, payload.id):
        raise ConflictError(f"Camera '{payload.id}' already exists")
    model_data = payload.model_dump()
    # Denormalise room_name from room_id, or require an explicit custom name.
    if model_data.get("room_id") is not None:
        model_data["room_name"] = _denormalise_room_name(db, model_data["room_id"])
    elif not model_data.get("room_name"):
        raise ValidationError("Select a room or provide a custom location name")
    cam = CtsCamera(**model_data)
    db.add(cam)
    db.commit()
    db.refresh(cam)
    logger.info("cts_camera_created", camera_id=cam.id)
    return _to_out(cam, db)


@router.get("/{camera_id}", response_model=CtsCameraOut)
def get_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> CtsCameraOut:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    return _to_out(cam, db)


@router.patch("/{camera_id}", response_model=CtsCameraOut)
def update_camera(
    camera_id: str,
    payload: CtsCameraUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
) -> CtsCameraOut:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    update_data = payload.model_dump(exclude_unset=True)
    # Denormalise room_name from room_id
    if "room_id" in update_data:
        if update_data["room_id"] is not None:
            update_data["room_name"] = _denormalise_room_name(db, update_data["room_id"])
        elif "room_name" not in update_data:
            update_data["room_name"] = ""
    for field, value in update_data.items():
        setattr(cam, field, value)
    db.commit()
    db.refresh(cam)
    logger.info("cts_camera_updated", camera_id=camera_id)
    return _to_out(cam, db)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
) -> None:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    db.delete(cam)
    db.commit()
    logger.info("cts_camera_deleted", camera_id=camera_id)


# ---------------------------------------------------------------------------
# Test-connect (does not persist anything)
# ---------------------------------------------------------------------------


@router.post("/test-connect")
async def rtsp_test_connect(
    body: dict,
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
    ingress: IngressAdminClient = Depends(get_ingress_admin_client),
) -> dict:
    cts_enabled()
    rtsp_url: str = body.get("rtsp_url", "")
    if not rtsp_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="rtsp_url is required",
        )
    try:
        return await ingress.test_connection(rtsp_url=rtsp_url)
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@router.get("/{camera_id}/snapshot")
async def get_snapshot(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
    ingress: IngressAdminClient = Depends(get_ingress_admin_client),
) -> Response:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    try:
        data = await ingress.snapshot(camera_id=camera_id)
        return Response(content=data, media_type="image/jpeg")
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/{camera_id}/health")
async def get_health(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
    ingress: IngressAdminClient = Depends(get_ingress_admin_client),
) -> dict:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    try:
        health = await ingress.stream_health(camera_id=camera_id)
        # Persist latest health snapshot for the UI to read without polling ingress.
        cam.health_json = health
        db.commit()
        return health
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        # Return cached health if upstream is unavailable.
        if cam.health_json:
            return {**cam.health_json, "_cached": True}
        raise _upstream_to_http(exc) from exc


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------


@router.post("/{camera_id}/reload", status_code=status.HTTP_204_NO_CONTENT)
async def reload_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
    ingress: IngressAdminClient = Depends(get_ingress_admin_client),
) -> None:
    cts_enabled()
    cam = db.get(CtsCamera, camera_id)
    if not cam:
        raise NotFoundError("Camera", camera_id)
    try:
        await ingress.reload_camera(camera_id=camera_id)
    except (UpstreamError, UpstreamTimeout, UpstreamUnavailable) as exc:
        raise _upstream_to_http(exc) from exc
