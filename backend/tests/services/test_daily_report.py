"""Tests for DailyReportService - end-of-day report compilation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from backend.models.person import ActivitySession, ActivityTypeEnum, DailyReport
from backend.services.daily_report import DailyReportService


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
    db.flush()
    return session


def _make_location_history(
    db,
    person_id="person123",
    room_name="bedroom",
    entered_at=None,
    exited_at=None,
):
    """Helper to create a PersonLocationHistory with prerequisite records."""
    from backend.models.person import PersonLocationHistory

    if entered_at is None:
        entered_at = datetime.now(UTC) - timedelta(hours=3)
    if exited_at is None:
        exited_at = entered_at + timedelta(hours=1)

    # Ensure prerequisite records exist
    _get_or_create_person(db, person_id)
    room_id = _get_or_create_room(db, room_name)

    history = PersonLocationHistory(
        person_id=person_id,
        room_id=room_id,
        room_name=room_name,
        entered_at=entered_at,
        exited_at=exited_at,
    )
    db.add(history)
    db.flush()
    return history


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
    db.flush()
    return activity


class TestDailyReportGeneration:
    """Tests for generate_daily_report method."""

    def test_generate_report_basic(self, db_factory):
        """Should generate a basic report with default values."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        report = service.generate_daily_report(
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
        assert isinstance(report["door_events"], dict)
        assert isinstance(report["exercise"], dict)
        assert isinstance(report["room_time"], dict)
        assert report["summary_text"] is None
        assert report["wellness_score"] is not None
        assert isinstance(report["wellness_alerts"], list)

    def test_generate_report_with_sleep_data(self, db_factory):
        """Should aggregate sleep sessions correctly."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create a sleep session
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=datetime.now(UTC) - timedelta(hours=8),
            closed_at=datetime.now(UTC) - timedelta(hours=0.5),
            duration_minutes=450,  # 7.5 hours
            status="closed",
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        sleep = report["sleep"]
        assert sleep["session_count"] == 1
        assert sleep["total_minutes"] == 450
        assert sleep["quality_score"] > 0
        assert sleep["disruptions"] == 0

    def test_generate_report_multiple_sleep_sessions(self, db_factory):
        """Should handle multiple sleep sessions (potential disruptions)."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create two sleep sessions
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=datetime.now(UTC) - timedelta(hours=10),
            closed_at=datetime.now(UTC) - timedelta(hours=8),
            duration_minutes=120,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=datetime.now(UTC) - timedelta(hours=4),
            closed_at=datetime.now(UTC) - timedelta(hours=2),
            duration_minutes=120,
            status="closed",
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        sleep = report["sleep"]
        assert sleep["session_count"] == 2
        assert sleep["total_minutes"] == 240
        assert sleep["disruptions"] == 1  # sessions - 1

    def test_generate_report_with_meal_data(self, db_factory):
        """Should aggregate meal prep and eating sessions."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create meal sessions
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.meal_prep,
            opened_at=datetime.now(UTC) - timedelta(hours=5),
            closed_at=datetime.now(UTC) - timedelta(hours=4.5),
            duration_minutes=30,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.meal_eating,
            opened_at=datetime.now(UTC) - timedelta(hours=4.5),
            closed_at=datetime.now(UTC) - timedelta(hours=4),
            duration_minutes=30,
            status="closed",
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        meals = report["meals"]
        assert meals["prep_count"] == 1
        assert meals["eating_count"] == 1
        assert meals["avg_duration_minutes"] == 30.0

    def test_generate_report_with_medication_data(self, db_factory):
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

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        medication = report["medication"]
        assert medication["doses_taken"] == 3
        assert medication["doses_due"] == 3
        assert medication["adherence_pct"] == 100.0

    def test_generate_report_with_partial_medication_adherence(self, db_factory):
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

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        medication = report["medication"]
        assert medication["doses_taken"] == 1
        assert medication["adherence_pct"] == 33.3  # 1/3 = 33.3%

    def test_generate_report_with_bathroom_visits(self, db_factory):
        """Should aggregate bathroom visit data."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create bathroom sessions
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.bathroom,
            opened_at=datetime.now(UTC) - timedelta(hours=6),
            closed_at=datetime.now(UTC) - timedelta(hours=5.8),
            duration_minutes=12,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.bathroom,
            opened_at=datetime.now(UTC) - timedelta(hours=3),
            closed_at=datetime.now(UTC) - timedelta(hours=2.7),
            duration_minutes=18,
            status="closed",
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        bathroom = report["bathroom_visits"]
        assert bathroom["visit_count"] == 2
        assert bathroom["total_minutes"] == 30
        assert bathroom["avg_duration_minutes"] == 15.0

    def test_generate_report_with_door_events(self, db_factory):
        """Should count door open/close events."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create door events
        _make_person_activity(
            db_factory(),
            person_id="person123",
            activity_type="door_open",
            detected_at=datetime.now(UTC) - timedelta(hours=5),
        )
        _make_person_activity(
            db_factory(),
            person_id="person123",
            activity_type="door_close",
            detected_at=datetime.now(UTC) - timedelta(hours=4.9),
        )
        _make_person_activity(
            db_factory(),
            person_id="person123",
            activity_type="door_open",
            detected_at=datetime.now(UTC) - timedelta(hours=3),
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        door = report["door_events"]
        assert door["open_count"] == 2
        assert door["close_count"] == 1

    def test_generate_report_with_exercise_data(self, db_factory):
        """Should aggregate exercise sessions."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create exercise sessions
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.exercise,
            opened_at=datetime.now(UTC) - timedelta(hours=4),
            closed_at=datetime.now(UTC) - timedelta(hours=3.25),
            duration_minutes=45,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.exercise,
            opened_at=datetime.now(UTC) - timedelta(hours=2),
            closed_at=datetime.now(UTC) - timedelta(hours=1.5),
            duration_minutes=30,
            status="closed",
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        exercise = report["exercise"]
        assert exercise["session_count"] == 2
        assert exercise["total_minutes"] == 75

    def test_generate_report_with_room_time(self, db_factory):
        """Should calculate time spent in each room."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create location history
        _make_location_history(
            db_factory(),
            person_id="person123",
            room_name="bedroom",
            entered_at=datetime.now(UTC) - timedelta(hours=8),
            exited_at=datetime.now(UTC) - timedelta(hours=2),
        )
        _make_location_history(
            db_factory(),
            person_id="person123",
            room_name="kitchen",
            entered_at=datetime.now(UTC) - timedelta(hours=2),
            exited_at=datetime.now(UTC),
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        room_time = report["room_time"]
        assert "bedroom" in room_time["distribution"]
        assert "kitchen" in room_time["distribution"]
        assert room_time["total_minutes"] > 0

    def test_generate_report_yesterday_date(self, db_factory):
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

        report = service.generate_daily_report(
            person_id="person123",
            date=yesterday,
            tz_name="UTC",
        )

        assert report["report_date"] == yesterday
        assert report["sleep"]["total_minutes"] == 450


class TestWellnessScoring:
    """Tests for wellness score and alerts computation."""

    def test_wellness_score_full_adherence(self, db_factory):
        """Should give high score with full medication adherence and good sleep."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Full medication adherence
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=datetime.now(UTC) - timedelta(hours=6),
            closed_at=datetime.now(UTC) - timedelta(hours=5.5),
            duration_minutes=30,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=datetime.now(UTC) - timedelta(hours=3),
            closed_at=datetime.now(UTC) - timedelta(hours=2.5),
            duration_minutes=30,
            status="closed",
        )
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.medication,
            opened_at=datetime.now(UTC) - timedelta(hours=1),
            closed_at=datetime.now(UTC) - timedelta(hours=0.5),
            duration_minutes=30,
            status="closed",
        )

        # Good sleep (8 hours)
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=datetime.now(UTC) - timedelta(hours=9),
            closed_at=datetime.now(UTC) - timedelta(hours=1),
            duration_minutes=480,
            status="closed",
        )

        # Exercise
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.exercise,
            opened_at=datetime.now(UTC) - timedelta(hours=4),
            closed_at=datetime.now(UTC) - timedelta(hours=3.5),
            duration_minutes=30,
            status="closed",
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        assert report["wellness_score"] is not None
        assert report["wellness_score"] > 70  # High score expected

    def test_wellness_score_sleep_deprivation_alert(self, db_factory):
        """Should generate sleep deprivation alert when no sleep data."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        report = service.generate_daily_report(
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

    def test_wellness_score_medication_missed_alert(self, db_factory):
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

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Should have medication alert
        alerts = report["wellness_alerts"]
        med_alerts = [a for a in alerts if a["type"] == "medication_missed"]
        assert len(med_alerts) >= 1
        assert med_alerts[0]["severity"] == "critical"

    def test_wellness_score_bathroom_frequency_alert(self, db_factory):
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

        report = service.generate_daily_report(
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

    def test_get_existing_report(self, db_factory):
        """Should retrieve an existing report from database."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Generate a report first
        report = service.generate_daily_report(
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

    def test_get_nonexistent_report(self, db_factory):
        """Should return None for non-existent report."""
        service = DailyReportService(db_factory)

        retrieved = service.get_report("person123", "2024-01-01")

        assert retrieved is None


class TestReportUpsert:
    """Tests for report upsertion to database."""

    def test_upsert_creates_new_report(self, db_factory):
        """Should create a new report record."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        service.generate_daily_report(
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

    def test_upsert_updates_existing_report(self, db_factory):
        """Should update existing report when regenerated."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Generate first report
        service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Generate again (should update)
        service.generate_daily_report(
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

    def test_service_with_scene_analysis_client(self, db_factory):
        """Should accept optional scene analysis client."""
        mock_client = MagicMock()
        service = DailyReportService(db_factory, scene_analysis_client=mock_client)

        assert service._scene_analysis_client == mock_client

    def test_service_without_scene_analysis_client(self, db_factory):
        """Should work without scene analysis client."""
        service = DailyReportService(db_factory)

        assert service._scene_analysis_client is None


class TestRoomTimeAggregation:
    """Tests for room time aggregation edge cases."""

    def test_room_time_with_no_exited_at(self, db_factory):
        """Should handle location history with no exit time."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        _make_location_history(
            db_factory(),
            person_id="person123",
            room_name="bedroom",
            entered_at=datetime.now(UTC) - timedelta(hours=5),
            exited_at=None,  # Still in room
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        assert "bedroom" in report["room_time"]["distribution"]

    def test_room_time_overlapping_periods(self, db_factory):
        """Should handle overlapping location history periods."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create overlapping periods
        _make_location_history(
            db_factory(),
            person_id="person123",
            room_name="bedroom",
            entered_at=datetime.now(UTC) - timedelta(hours=5),
            exited_at=datetime.now(UTC) - timedelta(hours=3),
        )
        _make_location_history(
            db_factory(),
            person_id="person123",
            room_name="kitchen",
            entered_at=datetime.now(UTC) - timedelta(hours=4),
            exited_at=datetime.now(UTC) - timedelta(hours=2),
        )

        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )

        # Both rooms should have time recorded
        assert "bedroom" in report["room_time"]["distribution"]
        assert "kitchen" in report["room_time"]["distribution"]


class TestDailyReportTimezoneHandling:
    """Tests for timezone-aware date handling."""

    def test_report_with_different_timezone(self, db_factory):
        """Should handle reports with different timezone."""
        service = DailyReportService(db_factory)
        today = datetime.now(UTC).date().isoformat()

        # Create session
        _make_activity_session(
            db_factory(),
            person_id="person123",
            activity_type=ActivityTypeEnum.sleep,
            opened_at=datetime.now(UTC) - timedelta(hours=8),
            closed_at=datetime.now(UTC) - timedelta(hours=0.5),
            duration_minutes=450,
            status="closed",
        )

        # Generate with America/New_York timezone
        report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="America/New_York",
        )

        assert report["tz_name"] == "America/New_York"
        assert report["sleep"]["total_minutes"] == 450

    def test_report_midnight_boundary(self, db_factory):
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
        today_report = service.generate_daily_report(
            person_id="person123",
            date=today,
            tz_name="UTC",
        )
        assert today_report["sleep"]["total_minutes"] == 480

        # Should not appear in yesterday's report
        yesterday_report = service.generate_daily_report(
            person_id="person123",
            date=yesterday,
            tz_name="UTC",
        )
        assert yesterday_report["sleep"]["total_minutes"] == 0
