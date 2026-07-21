"""Tests for DailyReportService - end-of-day report compilation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from backend.models.person import ActivitySession, ActivityTypeEnum, DailyReport
from backend.services.daily_report import DailyReportService
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService


def _get_or_create_room(db, name: str) -> int:
    """Get existing room by name or create a new one, return room id."""
    from backend.models.room import Room

    room = db.query(Room).filter(Room.name == name).first()
    if room:
        return room.id
    new_room = Room(name=name)
    db.add(new_room)
    db.flush()
    return new_room.id


def _get_or_create_person(db, person_id: str, name: str = "Test User") -> None:
    """Create household member if not exists."""
    from backend.models.person import HouseholdMember

    person = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not person:
        new_person = HouseholdMember(id=person_id, name=name)
        db.add(new_person)
        db.flush()


def _make_activity_session(
    db,
    person_id="person123",
    activity_type=ActivityTypeEnum.sleep,
    opened_at=None,
    closed_at=None,
    duration_minutes=60,
    status="closed",
    room_name="bedroom",
):
    """Helper to create an ActivitySession with prerequisite records."""
    if opened_at is None:
        opened_at = datetime.now(UTC) - timedelta(hours=2)
    if closed_at is None:
        closed_at = opened_at + timedelta(minutes=duration_minutes)

    # Ensure prerequisite records exist
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
        duration_minutes=duration_minutes,
    )
    db.add(session)
    db.commit()
    return session


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
    entered_at=None,
) -> None:
    """Ingest one room observation through PersonLocationService's real
    state machine (M32: room_segments is the room-time source, not the
    legacy PersonLocationHistory table). A later call with a different
    room_name closes the prior segment and opens the new one, exactly as
    production ingestion does; the last segment stays open (clamped by
    ``effective_exited_at`` at aggregation time)."""
    if entered_at is None:
        entered_at = datetime.now(UTC) - timedelta(hours=3)

    # Ensure prerequisite records exist, and commit before the location
    # service opens its own session: an uncommitted Room/HouseholdMember row
    # would make that session's FK-referencing insert block indefinitely
    # waiting on this transaction (a same-process deadlock, not a real
    # contention case).
    _get_or_create_person(db, person_id)
    room_id = _get_or_create_room(db, room_name)
    db.commit()

    await location_service.ingest_observation(
        person_id=person_id,
        observed_at=entered_at,
        source="world_tracker",
        room_id=room_id,
        confidence=0.9,
        metadata={"room_name": room_name},
    )


def _make_person_activity(
    db,
    person_id="person123",
    activity_type="door_open",
    detected_at=None,
    room_name="front_door",
):
    """Helper to create a PersonActivity with prerequisite records."""
    from backend.models.person import PersonActivity

    if detected_at is None:
        detected_at = datetime.now(UTC) - timedelta(hours=1)

    # Ensure prerequisite records exist
    _get_or_create_person(db, person_id)
    room_id = _get_or_create_room(db, room_name)

    activity = PersonActivity(
        person_id=person_id,
        activity_type=activity_type,
        room_id=room_id,
        room_name=room_name,
        detected_at=detected_at,
        confidence=0.9,
    )
    db.add(activity)
    db.commit()
    return activity


class TestDailyReportGeneration:
    """Tests for generate_daily_report method."""

    async def test_generate_report_basic(self, db_factory):
        """Should generate a basic report with default values."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        assert report["person_id"] == "person123"
        assert report["report_date"] == today
        assert report["tz_name"] == "UTC"
        assert "generated_at" in report
        assert isinstance(report["sleep"], dict)
        assert isinstance(report["meals"], dict)
        assert isinstance(report["medication"], dict)
        assert isinstance(report["bathroom_visits"], dict)
        assert isinstance(report["exercise"], dict)
        assert isinstance(report["room_time"], dict)
        assert report["summary_text"] is None
        assert report["wellness_score"] is not None
        assert isinstance(report["wellness_alerts"], list)

    async def test_generate_report_with_sleep_data(self, db_factory):
        """Should aggregate sleep sessions correctly."""
        service = DailyReportService(db_factory)

        # Use a fixed reference time safely in the middle of a day to avoid
        # midnight-boundary flakiness when the wall clock crosses a day.
        now = datetime.now(UTC)
        ref_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if ref_time > now:
            ref_time = ref_time - timedelta(days=1)
        today = ref_time.date().isoformat()

        # Create a sleep session that closed on "today" (ref_time's date).
        # The session opened 8h before ref_time and closed 0.5h before ref_time,
        # so closed_at falls within the target day.
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=ref_time - timedelta(hours=8),
            closed_at=ref_time - timedelta(hours=0.5),
            duration_minutes=450,  # 7.5 hours
            status="closed",
        )

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        sleep = report["sleep"]
        assert sleep["session_count"] == 1
        assert sleep["total_minutes"] == 450
        assert sleep["quality_score"] > 0
        assert sleep["disruptions"] == 0

    async def test_generate_report_multiple_sleep_sessions(self, db_factory):
        """Should handle multiple sleep sessions (potential disruptions)."""
        service = DailyReportService(db_factory)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        # Ensure we're working with a time that's at least 12 hours into the day
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            # If 6pm hasn't happened yet today, use yesterday's 6pm
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Create two sleep sessions using the same db instance
        db = db_factory()
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=test_time - timedelta(hours=10),
            closed_at=test_time - timedelta(hours=8),
            duration_minutes=120,
            status="closed",
        )
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=test_time - timedelta(hours=4),
            closed_at=test_time - timedelta(hours=2),
            duration_minutes=120,
            status="closed",
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        sleep = report["sleep"]
        assert sleep["session_count"] == 2
        assert sleep["total_minutes"] == 240
        assert sleep["disruptions"] == 1  # sessions - 1

    async def test_generate_report_with_meal_data(self, db_factory):
        """Should aggregate meal prep and eating sessions."""
        service = DailyReportService(db_factory)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Create meal sessions using the same db instance
        db = db_factory()
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.meal_prep,
            opened_at=test_time - timedelta(hours=5),
            closed_at=test_time - timedelta(hours=4.5),
            duration_minutes=30,
            status="closed",
        )
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.meal_eating,
            opened_at=test_time - timedelta(hours=4.5),
            closed_at=test_time - timedelta(hours=4),
            duration_minutes=30,
            status="closed",
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        meals = report["meals"]
        assert meals["prep_count"] == 1
        assert meals["eating_count"] == 1
        assert meals["avg_duration_minutes"] == 30.0

    async def test_generate_report_with_medication_data(self, db_factory):
        """Should track medication doses taken."""
        service = DailyReportService(db_factory)
        now = datetime.now(UTC)
        today = now.date().isoformat()

        # Create three medication sessions (full adherence) within today
        db = db_factory()
        for _, hour in enumerate([8, 14, 20]):
            opened_at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            closed_at = opened_at + timedelta(minutes=30)
            _make_activity_session(
                db,
                person_id="person123",
                activity_type=ActivityTypeEnum.medication,
                opened_at=opened_at,
                closed_at=closed_at,
                duration_minutes=30,
                status="closed",
            )
        db.commit()
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        medication = report["medication"]
        assert medication["doses_taken"] == 3
        assert medication["doses_due"] == 3
        assert medication["adherence_pct"] == 100.0

    async def test_generate_report_with_partial_medication_adherence(self, db_factory):
        """Should calculate adherence percentage correctly."""
        service = DailyReportService(db_factory)
        now = datetime.now(UTC)
        today = now.date().isoformat()

        # Create only one medication session (out of 3 due) within today
        db = db_factory()
        opened_at = now.replace(hour=14, minute=0, second=0, microsecond=0)
        closed_at = opened_at + timedelta(minutes=30)
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=opened_at,
            closed_at=closed_at,
            duration_minutes=30,
            status="closed",
        )
        db.commit()
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        medication = report["medication"]
        assert medication["doses_taken"] == 1
        assert medication["adherence_pct"] == 33.3  # 1/3 = 33.3%

    async def test_generate_report_with_bathroom_visits(self, db_factory):
        """Should aggregate bathroom visit data."""
        service = DailyReportService(db_factory)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Create bathroom sessions using the same db instance
        db = db_factory()
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.bathroom,
            opened_at=test_time - timedelta(hours=6),
            closed_at=test_time - timedelta(hours=5.8),
            duration_minutes=12,
            status="closed",
        )
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.bathroom,
            opened_at=test_time - timedelta(hours=3),
            closed_at=test_time - timedelta(hours=2.7),
            duration_minutes=18,
            status="closed",
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        bathroom = report["bathroom_visits"]
        assert bathroom["visit_count"] == 2
        assert bathroom["total_minutes"] == 30
        assert bathroom["avg_duration_minutes"] == 15.0

    async def test_generate_report_with_exercise_data(self, db_factory):
        """Should aggregate exercise sessions."""
        service = DailyReportService(db_factory)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Create exercise sessions using the same db instance
        db = db_factory()
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.exercise,
            opened_at=test_time - timedelta(hours=4),
            closed_at=test_time - timedelta(hours=3.25),
            duration_minutes=45,
            status="closed",
        )
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.exercise,
            opened_at=test_time - timedelta(hours=2),
            closed_at=test_time - timedelta(hours=1.5),
            duration_minutes=30,
            status="closed",
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        exercise = report["exercise"]
        assert exercise["session_count"] == 2
        assert exercise["total_minutes"] == 75

    async def test_generate_report_with_room_time(self, db_factory):
        """Should calculate time spent in each room."""
        location_service = _make_location_service(db_factory)
        service = DailyReportService(db_factory, person_location_service=location_service)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Bedroom entry, then a kitchen transition closes it and opens the
        # kitchen segment (sequential, matching production ingestion).
        db = db_factory()
        await _seed_room_entry(
            db,
            location_service,
            room_name="bedroom",
            entered_at=test_time - timedelta(hours=8),
        )
        await _seed_room_entry(
            db,
            location_service,
            room_name="kitchen",
            entered_at=test_time - timedelta(hours=2),
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        room_time = report["room_time"]
        assert "bedroom" in room_time["distribution"]
        assert "kitchen" in room_time["distribution"]
        assert room_time["total_minutes"] > 0

    async def test_generate_report_yesterday_date(self, db_factory):
        """Should work for previous dates."""
        service = DailyReportService(db_factory)
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()

        # Calculate timestamps for yesterday (midnight to 7.5 hours later = 450 min sleep)
        yesterday_midnight = datetime.strptime(yesterday, "%Y-%m-%d").replace(tzinfo=UTC)
        yesterday_7h30m = yesterday_midnight + timedelta(hours=7, minutes=30)

        # Create a session from yesterday
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=yesterday_midnight,
            closed_at=yesterday_7h30m,
            duration_minutes=450,
            status="closed",
        )

        report = await service.generate_daily_report(
            person_id="person123",
            date=yesterday,
            tz_name="UTC",
        )

        assert report["report_date"] == yesterday
        assert report["sleep"]["total_minutes"] == 450


class TestWellnessScoring:
    """Tests for wellness score and alerts computation."""

    async def test_wellness_score_full_adherence(self, db_factory):
        """Should give high score with full medication adherence and good sleep."""
        service = DailyReportService(db_factory)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Full medication adherence
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=test_time - timedelta(hours=6),
            closed_at=test_time - timedelta(hours=5.5),
            duration_minutes=30,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=test_time - timedelta(hours=3),
            closed_at=test_time - timedelta(hours=2.5),
            duration_minutes=30,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=test_time - timedelta(hours=1),
            closed_at=test_time - timedelta(hours=0.5),
            duration_minutes=30,
            status="closed",
        )

        # Good sleep (8 hours)
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=test_time - timedelta(hours=9),
            closed_at=test_time - timedelta(hours=1),
            duration_minutes=480,
            status="closed",
        )

        # Exercise
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.exercise,
            opened_at=test_time - timedelta(hours=4),
            closed_at=test_time - timedelta(hours=3.5),
            duration_minutes=30,
            status="closed",
        )

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        assert report["wellness_score"] is not None
        assert report["wellness_score"] >= 70  # High score expected

    async def test_wellness_score_sleep_deprivation_alert(self, db_factory):
        """Should generate sleep deprivation alert when no sleep data."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Should have sleep deprivation alert
        alerts = report["wellness_alerts"]
        sleep_alerts = [a for a in alerts if a["type"] == "sleep_deprivation"]
        assert len(sleep_alerts) >= 1
        assert sleep_alerts[0]["severity"] == "warning"
        assert "No sleep data" in sleep_alerts[0]["message"]

    async def test_wellness_score_medication_missed_alert(self, db_factory):
        """Should generate medication missed alert for low adherence."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # No medication sessions
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=datetime.now(UTC) - timedelta(hours=8),
            closed_at=datetime.now(UTC) - timedelta(hours=0.5),
            duration_minutes=450,
            status="closed",
        )

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Should have medication alert
        alerts = report["wellness_alerts"]
        med_alerts = [a for a in alerts if a["type"] == "medication_missed"]
        assert len(med_alerts) >= 1
        assert med_alerts[0]["severity"] == "critical"

    async def test_wellness_score_bathroom_frequency_alert(self, db_factory):
        """Should generate bathroom frequency alert for excessive visits."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Calculate timestamps for today
        today_midnight = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=UTC)

        # Create 12 bathroom visits spread throughout today
        for i in range(12):
            visit_time = today_midnight + timedelta(hours=i * 2)
            _make_activity_session(
                db_factory(),
                person_id="person123",
                activity_type=ActivityTypeEnum.bathroom,
                opened_at=visit_time,
                closed_at=visit_time + timedelta(minutes=12),
                duration_minutes=12,
                status="closed",
            )

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Should have bathroom frequency alert
        alerts = report["wellness_alerts"]
        bathroom_alerts = [a for a in alerts if a["type"] == "bathroom_frequency"]
        assert len(bathroom_alerts) >= 1
        assert bathroom_alerts[0]["severity"] == "warning"


class TestReportRetrieval:
    """Tests for get_report method."""

    async def test_get_existing_report(self, db_factory):
        """Should retrieve an existing report from database."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Generate a report first
        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Retrieve it
        retrieved = service.get_report("person123", today)

        assert retrieved is not None
        assert retrieved["person_id"] == "person123"
        assert retrieved["report_date"] == today
        assert retrieved["wellness_score"] == report["wellness_score"]

    async def test_get_nonexistent_report(self, db_factory):
        """Should return None for non-existent report."""
        service = DailyReportService(db_factory)

        retrieved = service.get_report("person123", "2024-01-01")

        assert retrieved is None


class TestReportUpsert:
    """Tests for report upsertion to database."""

    async def test_upsert_creates_new_report(self, db_factory):
        """Should create a new report record."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Verify record exists
        db = db_factory()
        try:
            record = db.get(DailyReport, f"person123_{today}")
            assert record is not None
            assert record.status == "complete"
        finally:
            db.close()

    async def test_upsert_updates_existing_report(self, db_factory):
        """Should update existing report when regenerated."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Generate first report
        await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Generate again (should update)
        await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Verify record exists and status is complete
        db = db_factory()
        try:
            record = db.get(DailyReport, f"person123_{today}")
            assert record is not None
            assert record.status == "complete"
        finally:
            db.close()


class TestDailyReportServiceInit:
    """Tests for service initialization."""

    async def test_service_with_scene_analysis_client(self, db_factory):
        """Should accept optional scene analysis client."""
        mock_client = MagicMock()
        service = DailyReportService(db_factory, scene_analysis_client=mock_client)

        assert service._scene_analysis_client == mock_client

    async def test_service_without_scene_analysis_client(self, db_factory):
        """Should work without scene analysis client."""
        service = DailyReportService(db_factory)

        assert service._scene_analysis_client is None


class TestRoomTimeAggregation:
    """Tests for room time aggregation edge cases."""

    async def test_room_time_with_no_exited_at(self, db_factory):
        """Should handle a still-open segment (no exit yet)."""
        location_service = _make_location_service(db_factory)
        service = DailyReportService(db_factory, person_location_service=location_service)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        # Bedroom entered 5 hours ago, never left -> still an open segment.
        db = db_factory()
        await _seed_room_entry(
            db,
            location_service,
            room_name="bedroom",
            entered_at=test_time - timedelta(hours=5),
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        assert "bedroom" in report["room_time"]["distribution"]

    async def test_room_time_sequential_transitions(self, db_factory):
        """Should record time for each room across sequential transitions.

        The legacy PersonLocationHistory table allowed independently-written,
        overlapping rows for the same person; PersonLocationService's one-
        open-segment-per-person invariant makes that physically impossible
        (a person cannot be in two rooms at once), so this seeds the
        realistic sequential-transition equivalent instead.
        """
        location_service = _make_location_service(db_factory)
        service = DailyReportService(db_factory, person_location_service=location_service)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)
        today = test_time.date().isoformat()

        db = db_factory()
        await _seed_room_entry(
            db,
            location_service,
            room_name="bedroom",
            entered_at=test_time - timedelta(hours=5),
        )
        await _seed_room_entry(
            db,
            location_service,
            room_name="kitchen",
            entered_at=test_time - timedelta(hours=3),
        )
        db.close()

        report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Both rooms should have time recorded
        assert "bedroom" in report["room_time"]["distribution"]
        assert "kitchen" in report["room_time"]["distribution"]


class TestDailyReportTimezoneHandling:
    """Tests for timezone-aware date handling."""

    async def test_report_with_different_timezone(self, db_factory):
        """Should handle reports with different timezone."""
        service = DailyReportService(db_factory)

        # Use a specific date to avoid midnight boundary issues
        from zoneinfo import ZoneInfo

        # Create a date in America/New_York timezone
        ny_tz = ZoneInfo("America/New_York")
        test_date = datetime(2024, 6, 15, tzinfo=ny_tz)  # June 15, 2024 midnight NY time
        test_date_str = test_date.date().isoformat()

        # Create session that falls within June 15 in NY timezone
        # 10am NY time on June 15
        session_time = test_date.replace(hour=10)
        session_time_utc = session_time.astimezone(UTC)

        # Create session
        db = db_factory()
        _make_activity_session(
            db,
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=session_time_utc - timedelta(hours=7, minutes=30),
            closed_at=session_time_utc,
            duration_minutes=450,
            status="closed",
        )
        db.close()

        # Generate with America/New_York timezone
        report = await service.generate_daily_report(
            person_id="person123",
            date=test_date_str,
            tz_name="America/New_York",
        )

        assert report["tz_name"] == "America/New_York"
        assert report["sleep"]["total_minutes"] == 450

    async def test_report_midnight_boundary(self, db_factory):
        """Should correctly handle sessions near midnight boundary."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()

        # Calculate timestamps for yesterday 8pm to today 4am
        yesterday_midnight = datetime.strptime(yesterday, "%Y-%m-%d").replace(tzinfo=UTC)
        today_midnight = yesterday_midnight + timedelta(days=1)
        session_opened = yesterday_midnight + timedelta(hours=20)  # Yesterday 8pm
        session_closed = today_midnight + timedelta(hours=4)  # Today 4am

        # Create session that spans midnight
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=session_opened,
            closed_at=session_closed,
            duration_minutes=480,
            status="closed",
        )

        # Should appear in today's report (closed today)
        today_report = await service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )
        assert today_report["sleep"]["total_minutes"] == 480

        # Should not appear in yesterday's report
        yesterday_report = await service.generate_daily_report(
            person_id="person123",
            date=yesterday,
            tz_name="UTC",
        )
        assert yesterday_report["sleep"]["total_minutes"] == 0
