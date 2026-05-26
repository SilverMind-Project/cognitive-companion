"""Transit zone service for camera-blind room entry/exit detection (M2)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.transit_zone import TransitZone


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
