"""Tests for ZoneService."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.models.room import Room
from backend.services.person_location.types import FloorPoint
from backend.services.zones import ZoneService


@dataclass(frozen=True)
class _Location:
    room_id: int
    room_name: str = "Kitchen"


class _PersonLocation:
    def __init__(
        self,
        *,
        location: _Location | None,
        floor_point: FloorPoint | None,
    ) -> None:
        self.location = location
        self.floor_point = floor_point

    async def where_is(self, person_id: str) -> _Location | None:
        return self.location

    async def latest_floor_point(self, person_id: str, *, max_age_s: int = 30) -> FloorPoint | None:
        return self.floor_point


def _add_room(db_session, name: str) -> Room:
    room = Room(name=name)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    return room


def _square(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_create_then_list_in_room(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    svc = ZoneService(db_factory=db_factory, person_location_service=None)

    zone = svc.create_zone(room_id=room.id, name="sink", polygon=_square(0.0, 0.0, 1.0, 1.0))
    zones = svc.list_zones(room_id=room.id)

    assert zone.id == zones[0].id
    assert zones[0].name == "sink"


@pytest.mark.asyncio
async def test_current_zone_returns_zone_when_point_inside(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    person_location = _PersonLocation(
        location=_Location(room_id=room.id),
        floor_point=FloorPoint(x_m=0.5, y_m=0.5),
    )
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)
    svc.create_zone(room_id=room.id, name="sink", polygon=_square(0.0, 0.0, 1.0, 1.0))

    zone = await svc.current_zone("person-1")

    assert zone is not None
    assert zone.name == "sink"


@pytest.mark.asyncio
async def test_current_zone_none_when_point_in_no_zone(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    person_location = _PersonLocation(
        location=_Location(room_id=room.id),
        floor_point=FloorPoint(x_m=3.0, y_m=3.0),
    )
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)
    svc.create_zone(room_id=room.id, name="sink", polygon=_square(0.0, 0.0, 1.0, 1.0))

    assert await svc.current_zone("person-1") is None


@pytest.mark.asyncio
async def test_current_zone_none_when_no_floor_point(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    person_location = _PersonLocation(location=_Location(room_id=room.id), floor_point=None)
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)
    svc.create_zone(room_id=room.id, name="sink", polygon=_square(0.0, 0.0, 1.0, 1.0))

    assert await svc.current_zone("person-1") is None


@pytest.mark.asyncio
async def test_current_zone_none_when_room_unknown(db_factory) -> None:
    person_location = _PersonLocation(location=None, floor_point=FloorPoint(x_m=0.5, y_m=0.5))
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)

    assert await svc.current_zone("person-1") is None


@pytest.mark.asyncio
async def test_overlapping_zones_returns_smallest_and_logs(db_factory, db_session, caplog) -> None:
    room = _add_room(db_session, "Kitchen")
    person_location = _PersonLocation(
        location=_Location(room_id=room.id),
        floor_point=FloorPoint(x_m=0.5, y_m=0.5),
    )
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)
    svc.create_zone(room_id=room.id, name="large", polygon=_square(0.0, 0.0, 3.0, 3.0))
    svc.create_zone(room_id=room.id, name="small", polygon=_square(0.0, 0.0, 1.0, 1.0))

    zone = await svc.current_zone("person-1")

    assert zone is not None
    assert zone.name == "small"
    assert any("zone_overlap" in record.getMessage() for record in caplog.records)


def test_cameras_for_zone_returns_explicit_camera_ids(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    svc = ZoneService(db_factory=db_factory, person_location_service=None)
    zone = svc.create_zone(
        room_id=room.id,
        name="stove",
        polygon=_square(0.0, 0.0, 1.0, 1.0),
        camera_ids=["kitchen-cam-1", "kitchen-cam-2"],
    )

    assert svc.cameras_for_zone(zone.id) == ["kitchen-cam-1", "kitchen-cam-2"]


def test_update_zone_invalidates_geometry_cache(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    svc = ZoneService(db_factory=db_factory, person_location_service=None)
    zone = svc.create_zone(room_id=room.id, name="sink", polygon=_square(0.0, 0.0, 1.0, 1.0))
    assert [z.id for z in svc.zones_for_point(room.id, (0.5, 0.5))] == [zone.id]

    svc.update_zone(zone.id, polygon=_square(2.0, 2.0, 3.0, 3.0))

    assert svc.zones_for_point(room.id, (0.5, 0.5)) == []


@pytest.mark.asyncio
async def test_wall_adjacent_point_uses_floor_point_not_visibility_polygon(
    db_factory, db_session
) -> None:
    room = _add_room(db_session, "Kitchen")
    person_location = _PersonLocation(
        location=_Location(room_id=room.id),
        floor_point=FloorPoint(x_m=0.95, y_m=0.5),
    )
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)
    svc.create_zone(
        room_id=room.id,
        name="wall-side-counter",
        polygon=_square(0.9, 0.0, 1.0, 1.0),
        camera_ids=["explicit-zone-camera"],
    )

    zone = await svc.current_zone("person-1")

    assert zone is not None
    assert zone.name == "wall-side-counter"
    assert svc.cameras_for_zone(zone.id) == ["explicit-zone-camera"]
