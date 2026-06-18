"""Sub-room zone CRUD and current-zone lookup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from shapely.geometry import Point
from shapely.prepared import PreparedGeometry, prep
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.room_zone import RoomZone
from backend.services.person_location.types import CurrentLocation, FloorPoint
from backend.services.zones.geometry import floor_meter_polygon

logger = get_logger(__name__)


class PersonLocationReader(Protocol):
    async def where_is(self, person_id: str) -> CurrentLocation | None: ...
    async def latest_floor_point(
        self, person_id: str, *, max_age_s: int = 30
    ) -> FloorPoint | None: ...


@dataclass(frozen=True)
class ZoneView:
    id: int
    room_id: int
    name: str
    purpose: str | None
    polygon: list[list[float]]
    camera_ids: list[str] | None
    is_enabled: bool


def _to_view(zone: RoomZone) -> ZoneView:
    return ZoneView(
        id=zone.id,
        room_id=zone.room_id,
        name=zone.name,
        purpose=zone.purpose,
        polygon=[list(vertex) for vertex in zone.polygon],
        camera_ids=list(zone.camera_ids) if zone.camera_ids is not None else None,
        is_enabled=zone.is_enabled,
    )


class ZoneService:
    """Manage room zones and resolve a resident's current floor-meter zone."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        person_location_service: PersonLocationReader | None,
    ) -> None:
        self._db_factory = db_factory
        self._person_location_service = person_location_service
        self._prepared: dict[int, PreparedGeometry] = {}
        self._areas: dict[int, float] = {}

    def set_person_location_service(
        self, person_location_service: PersonLocationReader | None
    ) -> None:
        self._person_location_service = person_location_service

    def list_zones(self, room_id: int | None = None) -> list[ZoneView]:
        db = self._db_factory()
        try:
            stmt = select(RoomZone).order_by(RoomZone.room_id, RoomZone.name, RoomZone.id)
            if room_id is not None:
                stmt = stmt.where(RoomZone.room_id == room_id)
            return [_to_view(zone) for zone in db.execute(stmt).scalars().all()]
        finally:
            db.close()

    def get_zone(self, zone_id: int) -> ZoneView:
        db = self._db_factory()
        try:
            zone = db.get(RoomZone, zone_id)
            if zone is None:
                raise NotFoundError("Room zone", zone_id)
            return _to_view(zone)
        finally:
            db.close()

    def create_zone(
        self,
        *,
        room_id: int,
        name: str,
        polygon: list[list[float]],
        purpose: str | None = None,
        camera_ids: list[str] | None = None,
        is_enabled: bool = True,
    ) -> ZoneView:
        self._validate_polygon(polygon)
        db = self._db_factory()
        try:
            existing = db.scalar(
                select(func.count())
                .select_from(RoomZone)
                .where(RoomZone.room_id == room_id, RoomZone.name == name)
            )
            if existing:
                raise ConflictError(f"Room zone '{name}' already exists in room '{room_id}'")
            zone = RoomZone(
                room_id=room_id,
                name=name,
                purpose=purpose,
                polygon=polygon,
                camera_ids=camera_ids,
                is_enabled=is_enabled,
            )
            db.add(zone)
            db.commit()
            db.refresh(zone)
            view = _to_view(zone)
            self._cache_zone(view)
            return view
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(f"Room zone '{name}' already exists in room '{room_id}'") from exc
        finally:
            db.close()

    def update_zone(
        self,
        zone_id: int,
        *,
        name: str | None = None,
        purpose: str | None = None,
        purpose_set: bool = False,
        polygon: list[list[float]] | None = None,
        camera_ids: list[str] | None = None,
        camera_ids_set: bool = False,
        is_enabled: bool | None = None,
    ) -> ZoneView:
        if polygon is not None:
            self._validate_polygon(polygon)
        db = self._db_factory()
        try:
            zone = db.get(RoomZone, zone_id)
            if zone is None:
                raise NotFoundError("Room zone", zone_id)
            if name is not None:
                duplicate = db.scalar(
                    select(func.count())
                    .select_from(RoomZone)
                    .where(
                        RoomZone.room_id == zone.room_id,
                        RoomZone.name == name,
                        RoomZone.id != zone_id,
                    )
                )
                if duplicate:
                    raise ConflictError(
                        f"Room zone '{name}' already exists in room '{zone.room_id}'"
                    )
                zone.name = name
            if purpose_set:
                zone.purpose = purpose
            if polygon is not None:
                zone.polygon = polygon
            if camera_ids_set:
                zone.camera_ids = camera_ids
            if is_enabled is not None:
                zone.is_enabled = is_enabled
            db.commit()
            db.refresh(zone)
            view = _to_view(zone)
            self._cache_zone(view)
            return view
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(
                f"Room zone update conflicts with an existing zone: {zone_id}"
            ) from exc
        finally:
            db.close()

    def delete_zone(self, zone_id: int) -> None:
        db = self._db_factory()
        try:
            zone = db.get(RoomZone, zone_id)
            if zone is None:
                raise NotFoundError("Room zone", zone_id)
            db.delete(zone)
            db.commit()
            self._invalidate(zone_id)
        finally:
            db.close()

    def zones_in_room(self, room_id: int) -> list[ZoneView]:
        db = self._db_factory()
        try:
            stmt = (
                select(RoomZone)
                .where(RoomZone.room_id == room_id, RoomZone.is_enabled.is_(True))
                .order_by(RoomZone.name, RoomZone.id)
            )
            return [_to_view(zone) for zone in db.execute(stmt).scalars().all()]
        finally:
            db.close()

    def cameras_for_zone(self, zone_id: int) -> list[str]:
        zone = self.get_zone(zone_id)
        return list(zone.camera_ids or [])

    async def current_zone(self, person_id: str) -> ZoneView | None:
        person_location = self._person_location_service
        if person_location is None:
            logger.info("current_zone_skipped", person_id=person_id, reason="no_location_service")
            return None

        location = await person_location.where_is(person_id)
        if location is None:
            return None

        floor_point = await person_location.latest_floor_point(person_id)
        if floor_point is None:
            return None

        matches = self.zones_for_point(location.room_id, (floor_point.x_m, floor_point.y_m))
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        matches.sort(key=lambda zone: self._area_for(zone))
        logger.warning(
            "zone_overlap",
            person_id=person_id,
            room_id=location.room_id,
            zone_ids=[zone.id for zone in matches],
            selected_zone_id=matches[0].id,
        )
        return matches[0]

    def zones_for_point(self, room_id: int, point_m: tuple[float, float]) -> list[ZoneView]:
        """Return enabled zones containing a floor-meter point in a room."""
        zones = self.zones_in_room(room_id)
        point = Point(point_m)
        matches: list[ZoneView] = []
        for zone in zones:
            prepared = self._prepared_for(zone)
            if prepared.covers(point):
                matches.append(zone)
        return matches

    def _prepared_for(self, zone: ZoneView) -> PreparedGeometry:
        prepared = self._prepared.get(zone.id)
        if prepared is None:
            self._cache_zone(zone)
            prepared = self._prepared[zone.id]
        return prepared

    def _cache_zone(self, zone: ZoneView) -> None:
        polygon = floor_meter_polygon(zone.polygon)
        if polygon is None:
            self._invalidate(zone.id)
            raise ValidationError("Room zone polygon must have at least three vertices")
        self._prepared[zone.id] = prep(polygon)
        self._areas[zone.id] = float(polygon.area)

    def _area_for(self, zone: ZoneView) -> float:
        area = self._areas.get(zone.id)
        if area is None:
            self._cache_zone(zone)
            area = self._areas[zone.id]
        return area

    def _invalidate(self, zone_id: int) -> None:
        self._prepared.pop(zone_id, None)
        self._areas.pop(zone_id, None)

    def _validate_polygon(self, polygon: list[list[float]]) -> None:
        if floor_meter_polygon(polygon) is None:
            raise ValidationError("Room zone polygon must have at least three vertices")
