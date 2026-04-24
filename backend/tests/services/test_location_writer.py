"""Unit tests for :class:`LocationWriter`.

Exercises the two core flows: (1) first-sighting insert, (2) room change
producing a close+insert pair on PersonLocationHistory, and (3) the
source-authority veto path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.models.person import HouseholdMember, PersonLocationHistory, PersonLocationState
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
                "tracklet_id": "t-1",
                "global_track_id": "gt-1",
                "identity_id": person_id,
                "identity_confidence": identity_conf,
                "bbox": {"x_min": 10, "y_min": 10, "x_max": 100, "y_max": 200},
            }
        ],
    }


@pytest.fixture
def writer(db_factory):
    _register_member(db_factory, "grandma")
    return LocationWriter(db_factory=db_factory)


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
                db.query(PersonLocationHistory)
                .order_by(PersonLocationHistory.entered_at)
                .all()
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
            db_factory=db_factory, authority=SourceAuthority(cts_lock_s=60)
        )

        # Write current state from "now".
        await writer.apply(_event("grandma", "kitchen"))

        # Replay a stale event from 5 minutes ago: should not overwrite.
        stale = datetime.now(UTC) - timedelta(minutes=5)
        await writer.apply(
            _event("grandma", "bathroom", event_time=stale)
        )

        db = db_factory()
        try:
            state = db.query(PersonLocationState).one()
            assert state.current_room_name == "kitchen"
        finally:
            db.close()
