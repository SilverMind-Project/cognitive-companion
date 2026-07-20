"""Tests for ActivityTimelineService - unified chronological event feed.

M32: the location/sighting sources are backed by PersonLocationService
(room_segments / observations), not the legacy PersonLocationHistory /
PersonSighting tables. See
codebase-hardening-m32-cc-location-read-unification.md.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.models.person import ActivitySession, ActivityTypeEnum, HouseholdMember, PersonActivity
from backend.services.activity_timeline import ActivityTimelineService
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService


def _get_or_create_room(db, name: str) -> int:
    from backend.models.room import Room

    room = db.query(Room).filter(Room.name == name).first()
    if room:
        return room.id
    new_room = Room(name=name)
    db.add(new_room)
    db.flush()
    return new_room.id


def _get_or_create_person(db, person_id: str) -> None:
    person = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not person:
        db.add(HouseholdMember(id=person_id, name="Test User"))
        db.flush()


def _make_activity_session(
    db,
    person_id="person123",
    activity_type=ActivityTypeEnum.sleep,
    opened_at=None,
    closed_at=None,
    room_name="bedroom",
    status="closed",
):
    if opened_at is None:
        opened_at = datetime.now(UTC) - timedelta(hours=2)
    if closed_at is None:
        closed_at = opened_at + timedelta(minutes=60)
    _get_or_create_person(db, person_id)
    room_id = _get_or_create_room(db, room_name)
    session = ActivitySession(
        id=f"{person_id}_{activity_type.value}_{opened_at.isoformat()}",
        person_id=person_id,
        activity_type=activity_type.value,
        room_id=room_id,
        room_name=room_name,
        opened_at=opened_at,
        closed_at=closed_at,
        status=status,
        timeout_minutes=720,
        duration_minutes=int((closed_at - opened_at).total_seconds() / 60),
    )
    db.add(session)
    db.commit()
    return session


def _make_person_activity(db, person_id="person123", activity_type="motion", detected_at=None):
    if detected_at is None:
        detected_at = datetime.now(UTC) - timedelta(hours=1)
    _get_or_create_person(db, person_id)
    activity = PersonActivity(
        person_id=person_id,
        activity_type=activity_type,
        detected_at=detected_at,
        confidence=0.9,
    )
    db.add(activity)
    db.commit()
    return activity


def _make_location_service(db_factory) -> PersonLocationService:
    return PersonLocationService(
        SqlAlchemyObservationRepository(db_factory),
        SqlAlchemySegmentRepository(db_factory),
        PersonLocationConfig(),
    )


async def _seed_room_entry(
    db,
    location_service: PersonLocationService,
    *,
    person_id="person123",
    room_name="bedroom",
    observed_at,
    source="world_tracker",
) -> None:
    """Ingest one observation through the real state machine. Commits room/
    person rows first: an uncommitted row would make the location service's
    separate FK-referencing session block indefinitely on this transaction."""
    _get_or_create_person(db, person_id)
    room_id = _get_or_create_room(db, room_name)
    db.commit()

    await location_service.ingest_observation(
        person_id=person_id,
        observed_at=observed_at,
        source=source,
        room_id=room_id,
        confidence=0.9,
        metadata={"room_name": room_name},
    )


class TestGetTimelineSources:
    """Characterization: each source contributes the documented event shape."""

    async def test_get_timeline_combines_activity_and_session_events(self, db_factory):
        """Activity and session sources are unaffected by M32 (not migrated)."""
        db = db_factory()
        _make_person_activity(db, activity_type="motion")
        _make_activity_session(db, activity_type=ActivityTypeEnum.sleep)
        db.close()

        service = ActivityTimelineService(db_factory, person_location_service=None)
        events = await service.get_timeline(person_id="person123", limit=100)

        sources = {e["source"] for e in events}
        assert "activity" in sources
        assert "session" in sources

    async def test_get_location_events_room_entered_and_transited(self, db_factory):
        """A room transition closes the first segment (room_transited) and
        opens the next (room_entered, still open)."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=location_service)

        now = datetime.now(UTC)
        db = db_factory()
        await _seed_room_entry(
            db, location_service, room_name="bedroom", observed_at=now - timedelta(hours=2)
        )
        await _seed_room_entry(
            db, location_service, room_name="kitchen", observed_at=now - timedelta(hours=1)
        )
        db.close()

        events = await service.get_timeline(
            person_id="person123",
            start_time=now - timedelta(hours=3),
            end_time=now + timedelta(hours=1),
            event_types=["location"],
        )

        assert len(events) == 2
        by_room = {e["room_name"]: e for e in events}
        assert by_room["bedroom"]["event_type"] == "room_transited"
        assert by_room["bedroom"]["metadata"]["exited_at"] is not None
        assert by_room["kitchen"]["event_type"] == "room_entered"
        assert by_room["kitchen"]["metadata"]["exited_at"] is None

    async def test_get_location_events_repeat_same_room_observation_is_one_segment(
        self, db_factory
    ):
        """Edge case: repeated observations in the same room do not fragment
        into multiple location events (the state machine no-ops the repeat)."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=location_service)

        now = datetime.now(UTC)
        db = db_factory()
        await _seed_room_entry(
            db, location_service, room_name="bedroom", observed_at=now - timedelta(hours=2)
        )
        await _seed_room_entry(
            db, location_service, room_name="bedroom", observed_at=now - timedelta(hours=1)
        )
        db.close()

        events = await service.get_timeline(
            person_id="person123",
            start_time=now - timedelta(hours=3),
            end_time=now + timedelta(hours=1),
            event_types=["location"],
        )

        assert len(events) == 1
        assert events[0]["room_name"] == "bedroom"

    async def test_get_sighting_events_from_observations(self, db_factory):
        """Sighting events are sourced from raw observations, source-tagged."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=location_service)

        now = datetime.now(UTC)
        db = db_factory()
        await _seed_room_entry(
            db,
            location_service,
            room_name="bedroom",
            observed_at=now - timedelta(hours=1),
            source="face_sighting",
        )
        db.close()

        events = await service.get_timeline(
            person_id="person123",
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(hours=1),
            event_types=["sighting"],
        )

        assert len(events) == 1
        assert events[0]["event_type"] == "person_sighted"
        assert events[0]["metadata"]["source"] == "face_sighting"

    async def test_get_sighting_events_downsampled_within_a_bucket(self, db_factory):
        """world_tracker can write several observations a second -- far
        denser than legacy PersonSighting's once-per-identification-run
        cadence. A dense cluster inside one 2-minute bucket must collapse
        to a single sighting event, not one per raw observation."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=location_service)

        now = datetime.now(UTC)
        # Bucket boundaries are aligned to the epoch (fixed 120s grid), not
        # to the first observation. Anchor 5s into a grid cell so the whole
        # 87s cluster provably lands in a single bucket regardless of when
        # `now` happens to fall.
        anchor_epoch = ((now - timedelta(hours=1)).timestamp() // 120) * 120 + 5
        base = datetime.fromtimestamp(anchor_epoch, tz=UTC)
        db = db_factory()
        # 30 observations, 3 seconds apart, spanning 87 seconds.
        for i in range(30):
            await _seed_room_entry(
                db,
                location_service,
                room_name="bedroom",
                observed_at=base + timedelta(seconds=3 * i),
                source="world_tracker",
            )
        db.close()

        events = await service.get_timeline(
            person_id="person123",
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(hours=1),
            limit=500,
            event_types=["sighting"],
        )

        assert len(events) == 1
        # The kept event is the most recent raw observation in the bucket.
        kept_at = datetime.fromisoformat(events[0]["timestamp"])
        assert kept_at == base + timedelta(seconds=3 * 29)

    async def test_get_sighting_events_not_clipped_to_newest_bucket(self, db_factory):
        """Downsampling must not collapse to only the most recent time
        window: bucketing runs over the whole matched range, not just the
        newest slice of raw rows (the bug in an earlier attempt at this
        that applied a query LIMIT before deduping)."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=location_service)

        now = datetime.now(UTC)
        db = db_factory()
        # Two dense clusters, hours apart: an old one and a recent one.
        for i in range(10):
            await _seed_room_entry(
                db,
                location_service,
                room_name="bedroom",
                observed_at=now - timedelta(hours=5) + timedelta(seconds=2 * i),
                source="world_tracker",
            )
        for i in range(10):
            await _seed_room_entry(
                db,
                location_service,
                room_name="kitchen",
                observed_at=now - timedelta(minutes=10) + timedelta(seconds=2 * i),
                source="world_tracker",
            )
        db.close()

        events = await service.get_timeline(
            person_id="person123",
            start_time=now - timedelta(hours=6),
            end_time=now + timedelta(hours=1),
            limit=500,
            event_types=["sighting"],
        )

        rooms = {e["room_name"] for e in events}
        assert rooms == {"bedroom", "kitchen"}

    async def test_get_timeline_missing_person_location_service_degrades_to_empty(
        self, db_factory
    ):
        """Missing-service path: location/sighting sources degrade to empty
        lists (CTS disabled) rather than raising; activity/session still work."""
        db = db_factory()
        _make_person_activity(db)
        db.close()

        service = ActivityTimelineService(db_factory, person_location_service=None)
        events = await service.get_timeline(
            person_id="person123", event_types=["location", "sighting", "activity"]
        )

        assert all(e["source"] != "location" for e in events)
        assert all(e["source"] != "sighting" for e in events)
        assert any(e["source"] == "activity" for e in events)

    async def test_set_person_location_service_rewires_late(self, db_factory):
        """Bootstrap pattern: the setter lets CTS-phase wiring attach the
        service after construction (matches companion_surface/zone/guided_task)."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=None)

        now = datetime.now(UTC)
        db = db_factory()
        await _seed_room_entry(db, location_service, observed_at=now - timedelta(hours=1))
        db.close()

        before = await service.get_timeline(person_id="person123", event_types=["location"])
        service.set_person_location_service(location_service)
        after = await service.get_timeline(person_id="person123", event_types=["location"])

        assert before == []
        assert len(after) == 1

    async def test_get_timeline_sorts_all_sources_by_timestamp_descending(self, db_factory):
        """Events from every source interleave in one timestamp-descending list."""
        location_service = _make_location_service(db_factory)
        service = ActivityTimelineService(db_factory, person_location_service=location_service)

        now = datetime.now(UTC)
        db = db_factory()
        _make_person_activity(db, activity_type="motion", detected_at=now - timedelta(minutes=30))
        await _seed_room_entry(db, location_service, observed_at=now - timedelta(minutes=90))
        db.close()

        events = await service.get_timeline(
            person_id="person123",
            start_time=now - timedelta(hours=3),
            end_time=now + timedelta(hours=1),
        )

        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps, reverse=True)
