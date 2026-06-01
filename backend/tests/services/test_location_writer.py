"""Unit tests for :class:`LocationWriter`.

Exercises the two core flows: (1) first-sighting insert, (2) room change
producing a close+insert pair on PersonLocationHistory, and (3) the
source-authority veto path.

Uses :class:`SqlAlchemyLocationRepository` wrapping the PostgreSQL session
provided by the ``db_factory`` conftest fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.models.person import HouseholdMember, PersonLocationHistory, PersonLocationState
from backend.services.cts.location_repository import SqlAlchemyLocationRepository
from backend.services.cts.location_writer import LocationWriter
from backend.services.cts.source_authority import SourceAuthority


def _register_member(db_factory, person_id: str) -> None:
    db = db_factory()
    try:
        if db.get(HouseholdMember, person_id) is None:
            db.add(HouseholdMember(id=person_id, name=person_id.title()))
            db.commit()
    finally:
        db.close()


def _event(
    person_id: str,
    room: str | None,
    camera: str = "kitchen-1",
    event_time: datetime | None = None,
    identity_conf: float = 0.95,
) -> dict:
    return {
        "event_id": "evt-1",
        "camera_id": camera,
        "event_time": (event_time or datetime.now(UTC)).isoformat(),
        "room_name": room,
        "detections": [
            {
                "id": "det-1",
                "detection_id": "t-1",
                "ph_id": "gt-1",
                "identity_id": person_id,
                "identity_confidence": identity_conf,
                "bbox": {"x_min": 10, "y_min": 10, "x_max": 100, "y_max": 200},
            }
        ],
    }


def _make_repo_factory(db_factory):
    """Wrap the db_factory to return SqlAlchemyLocationRepository instances."""

    def _factory():
        return SqlAlchemyLocationRepository(db_factory())

    return _factory


@pytest.fixture
def writer(db_factory):
    _register_member(db_factory, "grandma")
    return LocationWriter(repo_factory=_make_repo_factory(db_factory))


class TestFirstSighting:
    @pytest.mark.asyncio
    async def test_inserts_state_and_history(self, writer, db_factory):
        touched = await writer.apply(_event("grandma", "kitchen"))
        assert touched == ["grandma"]

        db = db_factory()
        try:
            state = db.query(PersonLocationState).one()
            assert state.person_id == "grandma"
            assert state.current_room_name == "kitchen"
            assert state.status == "home"

            history = db.query(PersonLocationHistory).all()
            assert len(history) == 1
            assert history[0].room_name == "kitchen"
            assert history[0].source == "cts"
            assert history[0].exited_at is None
        finally:
            db.close()


class TestRoomChange:
    @pytest.mark.asyncio
    async def test_closes_previous_and_opens_new(self, writer, db_factory):
        # First event: enter kitchen.
        t0 = datetime.now(UTC) - timedelta(minutes=5)
        await writer.apply(_event("grandma", "kitchen", event_time=t0))

        # Second event: move to living room.
        t1 = datetime.now(UTC) - timedelta(minutes=1)
        await writer.apply(_event("grandma", "living_room", event_time=t1))

        db = db_factory()
        try:
            history = (
                db.query(PersonLocationHistory).order_by(PersonLocationHistory.entered_at).all()
            )
            assert len(history) == 2
            assert history[0].room_name == "kitchen"
            assert history[0].exited_at is not None
            assert history[1].room_name == "living_room"
            assert history[1].exited_at is None

            state = db.query(PersonLocationState).one()
            assert state.current_room_name == "living_room"
        finally:
            db.close()


class TestNoIdentity:
    @pytest.mark.asyncio
    async def test_skips_detections_without_identity_id(self, writer, db_factory):
        event = _event("grandma", "kitchen")
        event["detections"][0]["identity_id"] = ""
        touched = await writer.apply(event)
        assert touched == []

        db = db_factory()
        try:
            assert db.query(PersonLocationState).count() == 0
            assert db.query(PersonLocationHistory).count() == 0
        finally:
            db.close()


class TestSourceAuthority:
    @pytest.mark.asyncio
    async def test_out_of_order_event_is_rejected(self, db_factory):
        _register_member(db_factory, "grandma")
        writer = LocationWriter(
            repo_factory=_make_repo_factory(db_factory),
            authority=SourceAuthority(cts_lock_s=60),
        )

        # Write current state from "now".
        await writer.apply(_event("grandma", "kitchen"))

        # Replay a stale event from 5 minutes ago: should not overwrite.
        stale = datetime.now(UTC) - timedelta(minutes=5)
        await writer.apply(_event("grandma", "bathroom", event_time=stale))

        db = db_factory()
        try:
            state = db.query(PersonLocationState).one()
            assert state.current_room_name == "kitchen"
        finally:
            db.close()


class TestMultipleDetections:
    @pytest.mark.asyncio
    async def test_multiple_persons_in_single_event(self, db_factory):
        """An event with detections for two different persons should create
        state and history for both."""
        _register_member(db_factory, "grandma")
        _register_member(db_factory, "grandpa")
        writer = LocationWriter(repo_factory=_make_repo_factory(db_factory))

        event = {
            "event_id": "evt-multi",
            "camera_id": "living-1",
            "event_time": datetime.now(UTC).isoformat(),
            "room_name": "living_room",
            "detections": [
                {
                    "id": "det-1",
                    "detection_id": "t-1",
                    "ph_id": "gt-1",
                    "identity_id": "grandma",
                    "identity_confidence": 0.95,
                },
                {
                    "id": "det-2",
                    "detection_id": "t-2",
                    "ph_id": "gt-2",
                    "identity_id": "grandpa",
                    "identity_confidence": 0.88,
                },
            ],
        }
        touched = await writer.apply(event)
        assert set(touched) == {"grandma", "grandpa"}

        db = db_factory()
        try:
            states = db.query(PersonLocationState).all()
            assert len(states) == 2
            assert {s.person_id for s in states} == {"grandma", "grandpa"}
        finally:
            db.close()


class TestNoRoomName:
    @pytest.mark.asyncio
    async def test_state_update_without_room_change(self, db_factory):
        """Event with no room_name should still upsert state but not
        create history rows."""
        _register_member(db_factory, "grandma")
        writer = LocationWriter(repo_factory=_make_repo_factory(db_factory))

        await writer.apply(_event("grandma", None))

        db = db_factory()
        try:
            # State should exist but with no room
            states = db.query(PersonLocationState).all()
            assert len(states) == 1

            # No history should be written when room_name is None
            history = db.query(PersonLocationHistory).all()
            assert len(history) == 0
        finally:
            db.close()
