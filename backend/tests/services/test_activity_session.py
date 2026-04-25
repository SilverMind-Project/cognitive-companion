"""Tests for ActivitySessionService - duration-aware activity sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.models.person import ActivitySession, ActivityTypeEnum, HouseholdMember
from backend.services.activity_session import (
    ACTIVITY_TIMEOUTS,
    ActivitySessionService,
)


def _make_person(db, person_id="person123"):
    """Create a HouseholdMember in the test DB."""
    member = HouseholdMember(id=person_id, name="Test Person", is_active=True)
    db.add(member)
    db.flush()
    return member


def _make_session(
    db,
    person_id="person123",
    activity_type=ActivityTypeEnum.sleep,
    opened_at=None,
    status="open",
    timeout_minutes=720,
):
    """Helper to create an ActivitySession."""
    _make_person(db, person_id)
    if opened_at is None:
        opened_at = datetime.now(UTC)
    # Accept both ActivityTypeEnum and plain strings
    atype = activity_type.value if isinstance(activity_type, ActivityTypeEnum) else activity_type
    session = ActivitySession(
        id=f"{person_id}_{atype}_{opened_at.isoformat()}",
        person_id=person_id,
        activity_type=atype,
        room_name="bedroom",
        opened_at=opened_at,
        closed_at=None if status == "open" else datetime.now(UTC),
        status=status,
        timeout_minutes=timeout_minutes,
        duration_minutes=None if status == "open" else 60,
    )
    db.add(session)
    db.flush()
    return session


class TestActivitySessionOpen:
    """Tests for open_session method - idempotent session opening."""

    def test_open_new_session(self, db_factory):
        """Should create a new session when none exists."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC)

        result = service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        assert result.session_id.startswith("person123_sleep_")
        assert result.person_id == "person123"
        assert result.activity_type == "sleep"
        assert result.room_name == "bedroom"
        assert result.opened_at == started_at
        assert result.timeout_minutes == 720  # sleep default
        assert result.was_existing is False

    def test_open_session_reuses_existing(self, db_factory):
        """Should return existing open session (idempotent)."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC)

        # Open first session
        result1 = service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        # Open again with same parameters
        result2 = service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="living_room",  # Different room should be ignored
            confidence=0.80,
            started_at=started_at + timedelta(minutes=5),
            start_event_id=None,
        )

        assert result1.session_id == result2.session_id
        assert result2.was_existing is True

    def test_open_session_different_activity_type(self, db_factory):
        """Should allow multiple open sessions for different activity types."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC)

        sleep_session = service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        bathroom_session = service.open_session(
            person_id="person123",
            activity_type="bathroom",
            room_name="bathroom",
            confidence=0.90,
            started_at=started_at + timedelta(minutes=10),
            start_event_id=None,
        )

        assert sleep_session.session_id != bathroom_session.session_id
        assert sleep_session.activity_type == "sleep"
        assert bathroom_session.activity_type == "bathroom"

    def test_open_session_uses_custom_timeout(self, db_factory):
        """Should use custom timeout when provided."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC)

        result = service.open_session(
            person_id="person123",
            activity_type="medication",  # Default is 30 min
            room_name="kitchen",
            confidence=0.85,
            started_at=started_at,
            start_event_id=None,
            timeout_minutes=45,
        )

        assert result.timeout_minutes == 45

    def test_open_session_invalid_activity_type(self, db_factory):
        """Should normalize invalid activity types to 'other'."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC)

        result = service.open_session(
            person_id="person123",
            activity_type="invalid_type_xyz",
            room_name="kitchen",
            confidence=0.85,
            started_at=started_at,
            start_event_id=None,
        )

        assert result.activity_type == "other"
        assert result.timeout_minutes == ACTIVITY_TIMEOUTS["other"]

    def test_open_session_unknown_type_defaults_to_other(self, db_factory):
        """Should handle unknown activity types gracefully."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC)

        result = service.open_session(
            person_id="person123",
            activity_type="unknown_activity",
            room_name="unknown_room",
            confidence=0.5,
            started_at=started_at,
            start_event_id=None,
        )

        assert result.activity_type == "other"
        assert result.timeout_minutes == 120  # Default timeout


class TestActivitySessionClose:
    """Tests for close_session method - explicit session closing."""

    def test_close_session_explicit(self, db_factory):
        """Should close session and compute duration."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC) - timedelta(minutes=30)

        # Open session
        open_result = service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        # Close session
        ended_at = datetime.now(UTC)
        close_result = service.close_session(
            person_id="person123",
            activity_type="sleep",
            ended_at=ended_at,
            end_event_id=None,
            closed_via="explicit",
        )

        assert close_result.session_id == open_result.session_id
        assert close_result.status == "closed"
        assert close_result.closed_via == "explicit"
        assert close_result.duration_minutes >= 30
        assert close_result.duration_minutes <= 31  # Allow 1 minute variance

    def test_close_session_timeout(self, db_factory):
        """Should close session marked as timed out."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC) - timedelta(minutes=100)

        # Open session with short timeout
        service.open_session(
            person_id="person123",
            activity_type="bathroom",  # 90 min timeout
            room_name="bathroom",
            confidence=0.90,
            started_at=started_at,
            start_event_id=None,
            timeout_minutes=90,
        )

        # Close as timeout
        ended_at = datetime.now(UTC)
        close_result = service.close_session(
            person_id="person123",
            activity_type="bathroom",
            ended_at=ended_at,
            end_event_id=None,
            closed_via="timeout",
        )

        assert close_result.closed_via == "timeout"

    def test_close_session_manual(self, db_factory):
        """Should close session marked as manually closed."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC) - timedelta(minutes=15)

        service.open_session(
            person_id="person123",
            activity_type="medication",
            room_name="kitchen",
            confidence=0.85,
            started_at=started_at,
            start_event_id=None,
        )

        close_result = service.close_session(
            person_id="person123",
            activity_type="medication",
            ended_at=datetime.now(UTC),
            end_event_id=None,
            closed_via="manual",
        )

        assert close_result.closed_via == "manual"

    def test_close_nonexistent_session_raises(self, db_factory):
        """Should raise ValueError when closing non-existent session."""
        service = ActivitySessionService(db_factory)

        with pytest.raises(ValueError, match="No open session found"):
            service.close_session(
                person_id="nonexistent",
                activity_type="sleep",
                ended_at=datetime.now(UTC),
                end_event_id=None,
            )

    def test_close_different_activity_type_raises(self, db_factory):
        """Should raise ValueError when closing non-matching activity type."""
        service = ActivitySessionService(db_factory)
        started_at = datetime.now(UTC) - timedelta(minutes=10)

        service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        with pytest.raises(ValueError, match="No open session found"):
            service.close_session(
                person_id="person123",
                activity_type="bathroom",  # Different type
                ended_at=datetime.now(UTC),
                end_event_id=None,
            )


class TestActivitySessionTimeout:
    """Tests for close_timed_out_sessions - auto-closing by timeout."""

    def test_close_timed_out_sessions(self, db_factory):
        """Should close sessions that exceed their timeout."""
        service = ActivitySessionService(db_factory)

        # Create an old session that should timeout
        db1 = db_factory()
        old_session = _make_session(
            db1,
            person_id="person123",
            activity_type="bathroom",  # 90 min timeout
            opened_at=datetime.now(UTC) - timedelta(minutes=100),
            status="open",
            timeout_minutes=90,
        )
        db1.commit()
        db1.close()

        # Create a recent session that should NOT timeout
        db2 = db_factory()
        recent_session = _make_session(
            db2,
            person_id="person456",
            activity_type="sleep",
            opened_at=datetime.now(UTC) - timedelta(minutes=10),
            status="open",
            timeout_minutes=720,
        )
        db2.commit()
        db2.close()

        results = service.close_timed_out_sessions()

        # Only the bathroom session should have timed out
        assert len(results) == 1
        assert results[0].session_id == old_session.id
        assert results[0].closed_via == "timeout"

        # Verify recent session is still open
        recent = db_factory().get(ActivitySession, recent_session.id)
        assert recent.status == "open"

    def test_close_timed_out_sessions_no_timeout(self, db_factory):
        """Should not close sessions without timeout configured."""
        service = ActivitySessionService(db_factory)
        db = db_factory()
        _make_session(
            db,
            person_id="person123",
            activity_type="other",
            opened_at=datetime.now(UTC) - timedelta(hours=10),
            status="open",
            timeout_minutes=None,  # No timeout
        )
        db.commit()
        db.close()

        results = service.close_timed_out_sessions()

        assert len(results) == 0

    def test_close_timed_out_sessions_with_observation_id(self, db_factory):
        """Should preserve observation_id when closing timed out."""
        service = ActivitySessionService(db_factory)

        db = db_factory()
        session = _make_session(
            db,
            person_id="person123",
            activity_type="bathroom",
            opened_at=datetime.now(UTC) - timedelta(minutes=100),
            status="open",
            timeout_minutes=90,
        )
        session.observation_id = 12345
        sid = session.id
        db.commit()
        db.close()

        results = service.close_timed_out_sessions()

        assert len(results) == 1
        db2 = db_factory()
        try:
            result = db2.get(ActivitySession, sid)
            assert result.observation_id == 12345
        finally:
            db2.close()


class TestActivitySessionQueryHelpers:
    """Tests for get_open_sessions and get_sessions_for_day helpers."""

    def test_get_open_sessions_all(self, db_factory):
        """Should return all open sessions."""
        service = ActivitySessionService(db_factory)
        now = datetime.now(UTC)

        service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=now - timedelta(minutes=10),
            start_event_id=None,
        )

        service.open_session(
            person_id="person456",
            activity_type="bathroom",
            room_name="bathroom",
            confidence=0.90,
            started_at=now - timedelta(minutes=5),
            start_event_id=None,
        )

        sessions = service.get_open_sessions()

        assert len(sessions) == 2

    def test_get_open_sessions_filtered_by_person(self, db_factory):
        """Should filter open sessions by person_id."""
        service = ActivitySessionService(db_factory)
        now = datetime.now(UTC)

        service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=now - timedelta(minutes=10),
            start_event_id=None,
        )

        service.open_session(
            person_id="person456",
            activity_type="bathroom",
            room_name="bathroom",
            confidence=0.90,
            started_at=now - timedelta(minutes=5),
            start_event_id=None,
        )

        sessions = service.get_open_sessions(person_id="person123")

        assert len(sessions) == 1
        assert sessions[0]["person_id"] == "person123"

    def test_get_open_sessions_empty(self, db_factory):
        """Should return empty list when no open sessions."""
        service = ActivitySessionService(db_factory)

        sessions = service.get_open_sessions()

        assert sessions == []

    def test_get_sessions_for_day(self, db_factory):
        """Should return closed sessions for a specific date."""
        service = ActivitySessionService(db_factory)
        now = datetime.now(UTC)

        # Create a closed session from today
        service.open_session(
            person_id="person123",
            activity_type="meal_eating",
            room_name="kitchen",
            confidence=0.90,
            started_at=now - timedelta(hours=2),
            start_event_id=None,
        )
        service.close_session(
            person_id="person123",
            activity_type="meal_eating",
            ended_at=now - timedelta(hours=1),
            end_event_id=None,
            closed_via="explicit",
        )

        # Create a closed session from yesterday
        service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=now - timedelta(days=2),
            start_event_id=None,
        )
        service.close_session(
            person_id="person123",
            activity_type="sleep",
            ended_at=now - timedelta(days=1),
            end_event_id=None,
            closed_via="explicit",
        )

        today_str = now.date().isoformat()
        sessions = service.get_sessions_for_day("person123", today_str)

        # Should only have today's session
        assert len(sessions) == 1
        assert sessions[0]["activity_type"] == "meal_eating"

    def test_get_sessions_for_day_multiple_people(self, db_factory):
        """Should correctly filter sessions by person."""
        service = ActivitySessionService(db_factory)

        # Use a fixed time to avoid midnight boundary issues
        now = datetime.now(UTC)
        test_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if test_time > now:
            test_time = test_time - timedelta(days=1)

        service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=test_time - timedelta(hours=5),
            start_event_id=None,
        )
        service.close_session(
            person_id="person123",
            activity_type="sleep",
            ended_at=test_time - timedelta(hours=3),
            end_event_id=None,
            closed_via="explicit",
        )

        service.open_session(
            person_id="person456",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.90,
            started_at=test_time - timedelta(hours=4),
            start_event_id=None,
        )
        service.close_session(
            person_id="person456",
            activity_type="sleep",
            ended_at=test_time - timedelta(hours=2),
            end_event_id=None,
            closed_via="explicit",
        )

        today_str = test_time.date().isoformat()
        sessions = service.get_sessions_for_day("person123", today_str)

        assert len(sessions) == 1
        assert sessions[0]["person_id"] == "person123"


class TestActivitySessionTimeouts:
    """Tests for activity type timeout configuration."""

    def test_all_activity_types_have_timeouts(self):
        """All activity types in ActivityTypeEnum should have timeouts."""
        for activity_type in ActivityTypeEnum:
            assert activity_type.value in ACTIVITY_TIMEOUTS, (
                f"Missing timeout for {activity_type.value}"
            )

    def test_timeout_values_reasonable(self):
        """Timeout values should be within reasonable bounds."""
        for activity_type, timeout in ACTIVITY_TIMEOUTS.items():
            assert timeout > 0, f"Timeout for {activity_type} must be positive"
            assert timeout <= 1440, (  # 24 hours max
                f"Timeout for {activity_type} should not exceed 24 hours"
            )

    def test_sleep_has_longest_timeout(self):
        """Sleep should have the longest timeout (12 hours)."""
        assert ACTIVITY_TIMEOUTS["sleep"] == 720
        assert ACTIVITY_TIMEOUTS["sleep"] == max(ACTIVITY_TIMEOUTS.values())

    def test_medication_has_shortest_timeout(self):
        """Medication should have the shortest timeout (30 minutes)."""
        assert ACTIVITY_TIMEOUTS["medication"] == 30
        assert ACTIVITY_TIMEOUTS["medication"] == min(ACTIVITY_TIMEOUTS.values())
