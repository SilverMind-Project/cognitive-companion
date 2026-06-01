"""R1 W3: Camera-blind bathroom inferred-dwell end-to-end test (C3).

Proves claim C3: a person who enters a camera-blind room through a transit
zone and stays 25 minutes causes an ``inferred_dwell_exceeded`` signal.

The test drives ``PersonLocationService`` and ``SignalStore`` directly with
the same SQLAlchemy repos that ``CTSRuntime`` wires in production. No parallel
harness; no mocks for the database layer.

Uses the testcontainer session fixture from ``backend/tests/conftest.py``.
Marked ``@pytest.mark.integration`` so CI selects it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService

# 20-minute threshold so a 25-minute dwell triggers the signal.
_TEST_CFG = PersonLocationConfig(inferred_dwell_max_s=20 * 60)

PERSON_ID = "test-person-bathroom"
T0 = datetime(2026, 5, 28, 10, 0, 0, tzinfo=UTC)
T_ENTER = T0
T_TICK = T0 + timedelta(minutes=25)


def _seed_room(db: Session, has_camera: bool = False) -> int:
    """Insert a room row and return its id."""
    from backend.models.room import Room

    room = Room(name=f"bathroom-{uuid.uuid4().hex[:8]}", has_camera=has_camera)
    db.add(room)
    db.flush()
    return int(room.id)


def _seed_person(db: Session, person_id: str) -> None:
    """Insert a minimal household_members row."""
    from backend.models.person import HouseholdMember

    existing = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if existing is None:
        p = HouseholdMember(id=person_id, name="Test Person")
        db.add(p)
        db.flush()


@pytest.mark.integration
class TestBathroomInferredDwellE2E:
    """C3: 25-minute camera-blind bathroom dwell produces inferred_dwell_exceeded."""

    @pytest.mark.asyncio
    async def test_inferred_dwell_exceeded_fires_after_threshold(self, db_session: Session, db_factory) -> None:
        """After 25 minutes in a camera-blind bathroom, inferred_dwell_exceeded fires."""
        bathroom_room_id = _seed_room(db_session, has_camera=False)
        hallway_room_id = _seed_room(db_session, has_camera=True)
        _seed_person(db_session, PERSON_ID)
        db_session.commit()

        obs_repo = SqlAlchemyObservationRepository(db_factory)
        seg_repo = SqlAlchemySegmentRepository(db_factory)
        svc = PersonLocationService(obs_repo, seg_repo, _TEST_CFG)

        # Person walks through the hallway→bathroom transit zone.
        await svc.ingest_room_transition(
            person_id=PERSON_ID,
            transit_zone_id="tz-hallway-bathroom",
            direction="enter",
            inside_room_id=bathroom_room_id,
            outside_room_id=hallway_room_id,
            floor_x_m=5.0,
            floor_y_m=2.0,
            event_time=T_ENTER,
        )

        # Verify segment exists with inferred_transit entry source.
        open_seg = await seg_repo.get_open(PERSON_ID)
        assert open_seg is not None, "Segment must be open after room transition"
        assert open_seg.entry_source == "inferred_transit", (
            f"entry_source must be 'inferred_transit', got '{open_seg.entry_source}'"
        )
        assert open_seg.is_inferred, "Segment must be marked as inferred"
        assert open_seg.room_id == bathroom_room_id

        # Advance time 25 minutes and fire the dwell tick.
        signals = await svc.tick(T_TICK)

        # Segment must now be closed by timeout.
        closed_seg = await seg_repo.get_open(PERSON_ID)
        assert closed_seg is None, "Open segment must be closed after inferred_dwell_exceeded tick"

        # Tick must have returned exactly one inferred_dwell_exceeded signal.
        assert len(signals) == 1, (
            f"Expected 1 inferred_dwell_exceeded signal, got {len(signals)}: {signals}"
        )
        sig = signals[0]
        assert sig["signal_type"] == "inferred_dwell_exceeded", (
            f"signal_type must be 'inferred_dwell_exceeded', got '{sig['signal_type']}'"
        )
        assert sig["person_id"] == PERSON_ID
        assert sig["severity"] == "warning"
        dwell_s = sig["value"]
        assert dwell_s == pytest.approx(25 * 60, abs=1), (
            f"signal value must be ~1500 s, got {dwell_s}"
        )

        # Persist the signal (mirroring what CTSRuntime does) and assert the DB row.
        from backend.services.cts.signal_store import SignalStore

        store = SignalStore(db_factory=db_factory)
        _, action = await store.upsert(sig)
        assert action == "new", f"Signal upsert must be 'new', got '{action}'"

        rows, total = await store.list_recent(
            person_id=PERSON_ID,
            signal_type="inferred_dwell_exceeded",
            window_hours=1,
        )
        assert total == 1, (
            f"dementia_signals must have exactly 1 inferred_dwell_exceeded row, got {total}"
        )
        assert rows[0]["signal_type"] == "inferred_dwell_exceeded"
        assert rows[0]["person_id"] == PERSON_ID

    @pytest.mark.asyncio
    async def test_dwell_below_threshold_does_not_fire(self, db_session: Session, db_factory) -> None:
        """A dwell shorter than the threshold must not emit a signal."""
        bathroom_room_id = _seed_room(db_session, has_camera=False)
        hallway_room_id = _seed_room(db_session, has_camera=True)
        _seed_person(db_session, PERSON_ID + "-short")
        db_session.commit()

        obs_repo = SqlAlchemyObservationRepository(db_factory)
        seg_repo = SqlAlchemySegmentRepository(db_factory)
        svc = PersonLocationService(obs_repo, seg_repo, _TEST_CFG)

        person = PERSON_ID + "-short"
        await svc.ingest_room_transition(
            person_id=person,
            transit_zone_id="tz-h-b",
            direction="enter",
            inside_room_id=bathroom_room_id,
            outside_room_id=hallway_room_id,
            floor_x_m=5.0,
            floor_y_m=2.0,
            event_time=T_ENTER,
        )

        # Only 10 minutes in — below the 20-minute threshold.
        signals = await svc.tick(T0 + timedelta(minutes=10))
        assert signals == [], f"Dwell below threshold must not emit signals, got {signals}"

        # Segment must still be open.
        open_seg = await seg_repo.get_open(person)
        assert open_seg is not None, "Segment must remain open below threshold"


@pytest.mark.integration
class TestBathroomSegmentInMemory:
    """Fast in-memory variant of C3 (no DB); validates pure state-machine logic."""

    @pytest.mark.asyncio
    async def test_inferred_dwell_exceeded_in_memory(self) -> None:
        """InMemory repos: 25-min dwell beyond threshold returns signal dict."""
        obs_repo = InMemoryObservationRepository()
        seg_repo = InMemorySegmentRepository()
        svc = PersonLocationService(obs_repo, seg_repo, _TEST_CFG)

        await svc.ingest_room_transition(
            person_id="mem-person",
            transit_zone_id="tz-1",
            direction="enter",
            inside_room_id=99,
            outside_room_id=1,
            floor_x_m=1.0,
            floor_y_m=1.0,
            event_time=T_ENTER,
        )

        signals = await svc.tick(T_TICK)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "inferred_dwell_exceeded"
        assert signals[0]["person_id"] == "mem-person"
