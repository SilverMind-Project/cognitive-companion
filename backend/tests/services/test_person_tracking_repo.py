"""M10 / TD-005: PersonTrackingService writes via :class:`LocationRepository`.

The service used to issue raw ORM queries inline; the M10 refactor delegates
all PersonLocationState / PersonLocationHistory persistence to
:class:`SqlAlchemyLocationRepository` so the CTS LocationWriter and the
camera-event ingestion path share one canonical write surface.

These tests exercise ``_update_location_state`` directly. The wider
``process_camera_event`` flow is covered by step-handler tests that mock
the service.
"""

from __future__ import annotations

import pytest

from backend.models.person import (
    HouseholdMember,
    PersonLocationHistory,
    PersonLocationState,
)
from backend.models.room import Room
from backend.services.camera_topology import RoomTransition
from backend.services.cts.source_authority import SourceAuthority
from backend.services.person_tracking import PersonTrackingService


class _FakePersonID:
    enabled = False


class _FakeHA:
    async def set_person_location(self, *_args, **_kwargs) -> None:  # pragma: no cover
        return None


@pytest.fixture
def service(db_factory):
    return PersonTrackingService(
        db_session_factory=db_factory,
        person_id_client=_FakePersonID(),  # type: ignore[arg-type]
        ha_client=_FakeHA(),  # type: ignore[arg-type]
        authority=SourceAuthority(),
        ws_manager=None,
    )


def _seed_member(db_factory, person_id: str = "grandma") -> None:
    db = db_factory()
    try:
        db.add(HouseholdMember(id=person_id, name="Grandma"))
        db.add(Room(id=1, name="Kitchen"))
        db.add(Room(id=2, name="Living Room"))
        db.commit()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_first_sighting_writes_state_and_history(service, db_factory) -> None:
    _seed_member(db_factory)
    db = db_factory()
    try:
        await service._update_location_state(
            db=db,
            person_id="grandma",
            room_name="Kitchen",
            sensor_id="cam-kitchen",
            confidence=0.9,
            source="camera",
        )
    finally:
        db.close()

    db = db_factory()
    try:
        state = (
            db.query(PersonLocationState).filter(PersonLocationState.person_id == "grandma").one()
        )
        assert state.current_room_name == "Kitchen"
        assert state.last_sensor_id == "recamera:cam-kitchen"
        assert state.confidence == pytest.approx(0.9)

        history = (
            db.query(PersonLocationHistory)
            .filter(PersonLocationHistory.person_id == "grandma")
            .all()
        )
        assert len(history) == 1
        assert history[0].room_name == "Kitchen"
        assert history[0].entered_at is not None
        assert history[0].exited_at is None
        assert history[0].source == "camera"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_room_change_closes_previous_history(service, db_factory) -> None:
    _seed_member(db_factory)

    db = db_factory()
    try:
        await service._update_location_state(
            db=db,
            person_id="grandma",
            room_name="Kitchen",
            sensor_id="cam-kitchen",
            confidence=0.9,
            source="camera",
        )
    finally:
        db.close()

    db = db_factory()
    try:
        await service._update_location_state(
            db=db,
            person_id="grandma",
            room_name="Living Room",
            sensor_id="cam-living",
            confidence=0.85,
            source="camera",
            room_transition=RoomTransition(
                person_id="grandma",
                person_name="Grandma",
                sensor_id="cam-living",
                semantic="entering",
                from_room_id=1,
                from_room_name="Kitchen",
                to_room_id=2,
                to_room_name="Living Room",
                direction_raw="left-to-right",
                confidence=0.85,
            ),
        )
    finally:
        db.close()

    db = db_factory()
    try:
        state = (
            db.query(PersonLocationState).filter(PersonLocationState.person_id == "grandma").one()
        )
        assert state.current_room_name == "Living Room"
        assert state.last_sensor_id == "recamera:cam-living"

        rows = (
            db.query(PersonLocationHistory)
            .filter(PersonLocationHistory.person_id == "grandma")
            .order_by(PersonLocationHistory.entered_at.asc())
            .all()
        )
        assert len(rows) == 2
        kitchen_row, living_row = rows
        assert kitchen_row.room_name == "Kitchen"
        assert kitchen_row.exited_at is not None  # closed
        assert living_row.room_name == "Living Room"
        assert living_row.exited_at is None  # currently open
        assert living_row.direction_semantic == "entering"
        assert living_row.from_room_name == "Kitchen"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_same_room_does_not_open_new_history(service, db_factory) -> None:
    _seed_member(db_factory)

    for _ in range(3):
        db = db_factory()
        try:
            await service._update_location_state(
                db=db,
                person_id="grandma",
                room_name="Kitchen",
                sensor_id="cam-kitchen",
                confidence=0.95,
                source="camera",
            )
        finally:
            db.close()

    db = db_factory()
    try:
        rows = (
            db.query(PersonLocationHistory)
            .filter(PersonLocationHistory.person_id == "grandma")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].exited_at is None
    finally:
        db.close()
