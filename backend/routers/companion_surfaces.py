"""Companion surface registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_companion_surface_service
from backend.schemas.companion_surface import (
    CompanionSurfaceCreate,
    CompanionSurfaceHeartbeat,
    CompanionSurfaceHeartbeatOut,
    CompanionSurfaceListOut,
    CompanionSurfaceOut,
    CompanionSurfaceUpdate,
)
from backend.services.companion_surface import CompanionSurfaceService, SurfaceDeviceState

router = APIRouter(prefix="/companion-surfaces", tags=["companion-surfaces"])


@router.get("", response_model=CompanionSurfaceListOut)
def list_companion_surfaces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: CompanionSurfaceService = Depends(get_companion_surface_service),
    _auth: AuthContext = Depends(require_permission("companion_surfaces:read")),
) -> CompanionSurfaceListOut:
    items, total = svc.list_surfaces(limit=limit, offset=offset)
    return CompanionSurfaceListOut(items=items, total=total)


@router.post("", response_model=CompanionSurfaceOut, status_code=201)
def create_companion_surface(
    payload: CompanionSurfaceCreate,
    svc: CompanionSurfaceService = Depends(get_companion_surface_service),
    _auth: AuthContext = Depends(require_permission("companion_surfaces:write")),
) -> CompanionSurfaceOut:
    return CompanionSurfaceOut.model_validate(
        svc.upsert_surface(
            surface_id=payload.id,
            name=payload.name,
            surface_type=payload.surface_type,
            room_id=payload.room_id,
            kind=payload.kind,
            is_enabled=payload.is_enabled,
        )
    )


@router.patch("/{surface_id}", response_model=CompanionSurfaceOut)
def update_companion_surface(
    surface_id: str,
    payload: CompanionSurfaceUpdate,
    svc: CompanionSurfaceService = Depends(get_companion_surface_service),
    _auth: AuthContext = Depends(require_permission("companion_surfaces:write")),
) -> CompanionSurfaceOut:
    update = payload.model_dump(exclude_unset=True)
    return CompanionSurfaceOut.model_validate(
        svc.update_surface(
            surface_id,
            name=payload.name,
            surface_type=payload.surface_type,
            kind=payload.kind,
            room_id=payload.room_id,
            room_id_set="room_id" in update,
            is_enabled=payload.is_enabled,
        )
    )


@router.post("/{surface_id}/heartbeat", response_model=CompanionSurfaceHeartbeatOut)
def record_companion_surface_heartbeat(
    surface_id: str,
    payload: CompanionSurfaceHeartbeat,
    svc: CompanionSurfaceService = Depends(get_companion_surface_service),
    _auth: AuthContext = Depends(require_permission("companion_surfaces:heartbeat")),
) -> CompanionSurfaceHeartbeatOut:
    svc.record_heartbeat(
        surface_id,
        reported_room_id=payload.reported_room_id,
        device=SurfaceDeviceState(
            platform=payload.platform,
            mic_active=payload.mic_active,
            camera_active=payload.camera_active,
            screen_awake=payload.screen_awake,
        ),
    )
    return CompanionSurfaceHeartbeatOut(status="ok")
