"""Transit zones CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.routers.cts_deps import cts_enabled
from backend.schemas.transit_zone import TransitZoneIn, TransitZoneOut, TransitZoneUpdate
from backend.services.cts.transit_zone_service import TransitZoneService

router = APIRouter(prefix="/cts/transit-zones", tags=["cts-transit-zones"])

logger = get_logger(__name__)


def _to_out(zone) -> TransitZoneOut:
    return TransitZoneOut(
        id=zone.id,
        name=zone.name,
        kind=zone.kind,
        polygon=zone.polygon,
        inside_room_id=zone.inside_room_id,
        outside_room_id=zone.outside_room_id,
        direction_vec=zone.direction_vec,
        created_at=zone.created_at.isoformat() if zone.created_at else "",
        updated_at=zone.updated_at.isoformat() if zone.updated_at else "",
    )


@router.get("", response_model=list[TransitZoneOut])
async def list_transit_zones(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> list[TransitZoneOut]:
    cts_enabled()
    svc = TransitZoneService(db)
    return [_to_out(z) for z in svc.list_zones()]


@router.get("/{zone_id}", response_model=TransitZoneOut)
async def get_transit_zone(
    zone_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> TransitZoneOut:
    cts_enabled()
    svc = TransitZoneService(db)
    zone = svc.get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Transit zone not found")
    return _to_out(zone)


@router.post("", response_model=TransitZoneOut, status_code=status.HTTP_201_CREATED)
async def create_transit_zone(
    body: TransitZoneIn,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
) -> TransitZoneOut:
    cts_enabled()
    svc = TransitZoneService(db)

    # Centralized polygon and room reference validation.
    from backend.services.cts.transit_zone_service import validate_transit_zone_polygon

    errors = validate_transit_zone_polygon(
        polygon=body.polygon,
        inside_room_id=body.inside_room_id,
        outside_room_id=body.outside_room_id,
        direction_vec=body.direction_vec,
    )
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    # Normalize direction vector.
    import math

    dx, dy = body.direction_vec
    mag = math.sqrt(dx * dx + dy * dy)
    norm_direction = [dx / mag, dy / mag] if mag > 0 else [1.0, 0.0]
    zone = svc.create_zone(
        name=body.name,
        kind=body.kind,
        polygon=body.polygon,
        inside_room_id=body.inside_room_id,
        outside_room_id=body.outside_room_id,
        direction_vec=norm_direction,
    )
    db.commit()
    return _to_out(zone)


@router.patch("/{zone_id}", response_model=TransitZoneOut)
async def update_transit_zone(
    zone_id: str,
    body: TransitZoneUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
) -> TransitZoneOut:
    cts_enabled()
    svc = TransitZoneService(db)

    # Validate polygon fields if any geometry-related fields are updated.
    from backend.services.cts.transit_zone_service import validate_transit_zone_polygon

    if (
        body.polygon is not None
        or body.inside_room_id is not None
        or body.outside_room_id is not None
    ):
        existing = svc.get_zone(zone_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Transit zone not found")
        poly = body.polygon if body.polygon is not None else existing.polygon
        inside = body.inside_room_id if body.inside_room_id is not None else existing.inside_room_id
        outside = (
            body.outside_room_id if body.outside_room_id is not None else existing.outside_room_id
        )
        dir_vec = body.direction_vec if body.direction_vec is not None else existing.direction_vec
        errors = validate_transit_zone_polygon(
            polygon=poly,
            inside_room_id=inside,
            outside_room_id=outside,
            direction_vec=dir_vec,
        )
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))

    kwargs = body.model_dump(exclude_unset=True)
    zone = svc.update_zone(zone_id, **kwargs)
    if zone is None:
        raise HTTPException(status_code=404, detail="Transit zone not found")
    db.commit()
    return _to_out(zone)


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transit_zone(
    zone_id: str,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("cts.cameras.write")),
) -> None:
    cts_enabled()
    svc = TransitZoneService(db)
    if not svc.delete_zone(zone_id):
        raise HTTPException(status_code=404, detail="Transit zone not found")
    db.commit()
