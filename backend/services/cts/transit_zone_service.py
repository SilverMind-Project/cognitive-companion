"""Transit zone service for camera-blind room entry/exit detection (M2).

WTR5: Added polygon and room reference validation.
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.transit_zone import TransitZone

logger = get_logger(__name__)


def validate_transit_zone_polygon(
    polygon: list[list[float]],
    inside_room_id: int | None = None,
    outside_room_id: int | None = None,
    direction_vec: list[float] | None = None,
) -> list[str]:
    """Validate a transit zone polygon and associated fields.

    Returns a list of validation error messages (empty list = valid).
    """
    errors: list[str] = []

    # Non-self-intersecting polygon with at least 3 vertices.
    if len(polygon) < 3:
        errors.append("polygon must have at least 3 vertices")
        return errors

    from shapely.geometry import Polygon

    try:
        poly = Polygon([(p[0], p[1]) for p in polygon])
    except Exception:
        errors.append("polygon geometry is invalid")
        return errors

    if not poly.is_valid:
        errors.append("polygon is self-intersecting or invalid")

    if poly.area <= 0:
        errors.append("polygon area must be greater than zero")

    # Transit zone must link exactly two distinct rooms.
    if inside_room_id is None or outside_room_id is None:
        errors.append("inside_room_id and outside_room_id are required")
    elif inside_room_id == outside_room_id:
        errors.append("inside_room_id and outside_room_id must be different")

    # Direction vector validation.
    if direction_vec is not None and len(direction_vec) >= 2:
        dx, dy = float(direction_vec[0]), float(direction_vec[1])
        mag = math.sqrt(dx * dx + dy * dy)
        if mag < 1e-6:
            errors.append("direction vector must have non-zero magnitude")
    else:
        errors.append("direction_vec is required")

    return errors


class TransitZoneService:
    """CRUD service for transit zones (door/threshold zones)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_zones(self) -> list[TransitZone]:
        return list(self._db.scalars(select(TransitZone).order_by(TransitZone.name)))

    def get_zone(self, zone_id: str) -> TransitZone | None:
        return self._db.get(TransitZone, zone_id)

    def create_zone(
        self,
        name: str,
        kind: str,
        polygon: list,
        inside_room_id: int,
        outside_room_id: int,
        direction_vec: list,
    ) -> TransitZone:
        zone = TransitZone(
            id=str(uuid.uuid4()),
            name=name,
            kind=kind,
            polygon=polygon,
            inside_room_id=inside_room_id,
            outside_room_id=outside_room_id,
            direction_vec=direction_vec,
        )
        self._db.add(zone)
        self._db.flush()
        return zone

    def update_zone(
        self,
        zone_id: str,
        *,
        name: str | None = None,
        kind: str | None = None,
        polygon: list | None = None,
        inside_room_id: int | None = None,
        outside_room_id: int | None = None,
        direction_vec: list | None = None,
    ) -> TransitZone | None:
        zone = self._db.get(TransitZone, zone_id)
        if zone is None:
            return None
        if name is not None:
            zone.name = name
        if kind is not None:
            zone.kind = kind
        if polygon is not None:
            zone.polygon = polygon
        if inside_room_id is not None:
            zone.inside_room_id = inside_room_id
        if outside_room_id is not None:
            zone.outside_room_id = outside_room_id
        if direction_vec is not None:
            zone.direction_vec = direction_vec
        self._db.flush()
        return zone

    def delete_zone(self, zone_id: str) -> bool:
        zone = self._db.get(TransitZone, zone_id)
        if zone is None:
            return False
        self._db.delete(zone)
        self._db.flush()
        return True
