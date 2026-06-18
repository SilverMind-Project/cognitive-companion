"""Sub-room zone endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.auth import AuthContext, require_permission
from backend.routers.dependencies import get_zone_service
from backend.schemas.room_zone import (
    RoomZoneCreate,
    RoomZoneListOut,
    RoomZoneOut,
    RoomZoneUpdate,
)
from backend.services.zones import ZoneService

router = APIRouter(tags=["room-zones"])


@router.get("/rooms/{room_id}/zones", response_model=RoomZoneListOut)
def list_room_zones(
    room_id: int,
    svc: ZoneService = Depends(get_zone_service),
    _auth: AuthContext = Depends(require_permission("room_zones:read")),
) -> RoomZoneListOut:
    items = [RoomZoneOut.model_validate(zone) for zone in svc.list_zones(room_id=room_id)]
    return RoomZoneListOut(items=items, total=len(items))


@router.post("/rooms/{room_id}/zones", response_model=RoomZoneOut, status_code=201)
def create_room_zone(
    room_id: int,
    payload: RoomZoneCreate,
    svc: ZoneService = Depends(get_zone_service),
    _auth: AuthContext = Depends(require_permission("room_zones:write")),
) -> RoomZoneOut:
    return RoomZoneOut.model_validate(
        svc.create_zone(
            room_id=room_id,
            name=payload.name,
            purpose=payload.purpose,
            polygon=payload.polygon,
            camera_ids=payload.camera_ids,
            is_enabled=payload.is_enabled,
        )
    )


@router.patch("/zones/{zone_id}", response_model=RoomZoneOut)
def update_room_zone(
    zone_id: int,
    payload: RoomZoneUpdate,
    svc: ZoneService = Depends(get_zone_service),
    _auth: AuthContext = Depends(require_permission("room_zones:write")),
) -> RoomZoneOut:
    update = payload.model_dump(exclude_unset=True)
    return RoomZoneOut.model_validate(
        svc.update_zone(
            zone_id,
            name=payload.name,
            purpose=payload.purpose,
            purpose_set="purpose" in update,
            polygon=payload.polygon,
            camera_ids=payload.camera_ids,
            camera_ids_set="camera_ids" in update,
            is_enabled=payload.is_enabled,
        )
    )


@router.delete("/zones/{zone_id}", status_code=204)
def delete_room_zone(
    zone_id: int,
    svc: ZoneService = Depends(get_zone_service),
    _auth: AuthContext = Depends(require_permission("room_zones:write")),
) -> None:
    svc.delete_zone(zone_id)


@router.get("/persons/{person_id}/current-zone", response_model=RoomZoneOut | None)
async def get_current_zone(
    person_id: str,
    svc: ZoneService = Depends(get_zone_service),
    _auth: AuthContext = Depends(require_permission("room_zones:read")),
) -> RoomZoneOut | None:
    zone = await svc.current_zone(person_id)
    return RoomZoneOut.model_validate(zone) if zone is not None else None
