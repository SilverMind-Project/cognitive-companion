"""Tests for SceneTrendFilter - scene trend context filter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.filters.builtin.scene_trend import SceneTrendFilter


def _ensure_person(db, person_id="person123"):
    """Ensure a HouseholdMember exists in the DB."""
    from backend.models.person import HouseholdMember

    person = db.get(HouseholdMember, person_id)
    if not person:
        person = HouseholdMember(id=person_id, name="Test Person", is_active=True)
        db.add(person)
        db.flush()


_UNSET = object()


def _make_location_entry(
    db, person_id="person123", room_name="bedroom", entered_at=None, exited_at=_UNSET
):
    """Create a PersonLocationHistory entry.

    Pass ``exited_at=None`` for an open (no-exit) entry, or omit it for
    the default closed entry (entered_at + 15 min).
    """
    from backend.models.person import PersonLocationHistory

    _ensure_person(db, person_id)

    if entered_at is None:
        entered_at = datetime.now(UTC) - timedelta(minutes=30)
    if exited_at is _UNSET:
        exited_at = entered_at + timedelta(minutes=15)

    entry = PersonLocationHistory(
        person_id=person_id,
        room_name=room_name,
        entered_at=entered_at,
        exited_at=exited_at,
    )
    db.add(entry)
    db.flush()
    return entry


def _make_activity(db, person_id="person123", activity_type="bathroom", detected_at=None):
    """Create a PersonActivity entry."""
    from backend.models.person import PersonActivity

    _ensure_person(db, person_id)

    if detected_at is None:
        detected_at = datetime.now(UTC) - timedelta(minutes=10)

    entry = PersonActivity(
        person_id=person_id,
        activity_type=activity_type,
        detected_at=detected_at,
    )
    db.add(entry)
    db.flush()
    return entry


FILTER = SceneTrendFilter()


class TestSceneTrendProlongedStay:
    """Tests for prolonged_stay trend detection."""

    def test_prolonged_stay_detected(self, db_factory):
        """Should detect when person stayed in room > threshold."""
        db = db_factory()
        now = datetime.now(UTC)

        # Create a long stay (60 min) in bedroom
        _make_location_entry(
            db,
            person_id="person123",
            room_name="bedroom",
            entered_at=now - timedelta(minutes=60),
            exited_at=None,  # still there (open session)
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "threshold_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is True
        db.close()

    def test_prolonged_stay_not_detected(self, db_factory):
        """Should not detect when stay is below threshold."""
        db = db_factory()
        now = datetime.now(UTC)

        # Create a short stay (10 min) that already ended
        _make_location_entry(
            db,
            person_id="person123",
            room_name="bedroom",
            entered_at=now - timedelta(minutes=20),
            exited_at=now - timedelta(minutes=10),
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "threshold_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_prolonged_stay_filtered_by_room(self, db_factory):
        """Should respect room_name filter for prolonged stay."""
        db = db_factory()
        now = datetime.now(UTC)

        # Long stay in kitchen, short stay in bedroom
        _make_location_entry(
            db,
            person_id="person123",
            room_name="kitchen",
            entered_at=now - timedelta(minutes=60),
            exited_at=None,
        )
        _make_location_entry(
            db,
            person_id="person123",
            room_name="bedroom",
            entered_at=now - timedelta(minutes=15),
            exited_at=now - timedelta(minutes=5),
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "room_name": "bedroom",
                "threshold_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "room_name": "kitchen",
                "threshold_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is True
        db.close()

    def test_prolonged_stay_missing_threshold(self, db_factory):
        """Should return False when threshold_minutes is not provided."""
        db = db_factory()
        now = datetime.now(UTC)

        _make_location_entry(
            db,
            person_id="person123",
            room_name="bedroom",
            entered_at=now - timedelta(minutes=60),
            exited_at=None,
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()


class TestSceneTrendFrequentVisits:
    """Tests for frequent_visits trend detection."""

    def test_frequent_visits_detected(self, db_factory):
        """Should detect when person visited room >= visit_count times."""
        db = db_factory()
        now = datetime.now(UTC)

        for i in range(6):
            _make_location_entry(
                db,
                person_id="person123",
                room_name="bathroom",
                entered_at=now - timedelta(minutes=(i * 10) + 5),
                exited_at=now - timedelta(minutes=i * 10),
            )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "frequent_visits",
                "room_name": "bathroom",
                "visit_count": 5,
                "within_minutes": 60,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is True
        db.close()

    def test_frequent_visits_not_detected(self, db_factory):
        """Should not detect when visits are below threshold."""
        db = db_factory()
        now = datetime.now(UTC)

        for i in range(3):
            _make_location_entry(
                db,
                person_id="person123",
                room_name="bathroom",
                entered_at=now - timedelta(minutes=(i * 15) + 5),
                exited_at=now - timedelta(minutes=i * 15),
            )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "frequent_visits",
                "room_name": "bathroom",
                "visit_count": 5,
                "within_minutes": 60,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_frequent_visits_without_room_filter(self, db_factory):
        """Should count visits across all rooms when no room_name filter."""
        db = db_factory()
        now = datetime.now(UTC)

        for i in range(4):
            _make_location_entry(
                db,
                person_id="person123",
                room_name="bedroom",
                entered_at=now - timedelta(minutes=(i * 10) + 5),
                exited_at=now - timedelta(minutes=i * 10),
            )
            _make_location_entry(
                db,
                person_id="person123",
                room_name="kitchen",
                entered_at=now - timedelta(minutes=(i * 10) + 8),
                exited_at=now - timedelta(minutes=i * 10 + 3),
            )
        db.commit()

        # 8 total visits (4 bedroom + 4 kitchen) >= 5
        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "frequent_visits",
                "visit_count": 5,
                "within_minutes": 60,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is True
        db.close()


class TestSceneTrendUnusualActivity:
    """Tests for unusual_activity trend detection."""

    def test_unusual_activity_detected(self, db_factory):
        """Should detect when activity count >= threshold."""
        db = db_factory()
        now = datetime.now(UTC)

        for i in range(6):
            _make_activity(
                db,
                person_id="person123",
                activity_type="bathroom",
                detected_at=now - timedelta(minutes=(i * 8) + 4),
            )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "unusual_activity",
                "activity_type": "bathroom",
                "activity_count": 5,
                "within_minutes": 60,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is True
        db.close()

    def test_unusual_activity_not_detected(self, db_factory):
        """Should not detect when activity count is below threshold."""
        db = db_factory()
        now = datetime.now(UTC)

        for i in range(2):
            _make_activity(
                db,
                person_id="person123",
                activity_type="cooking",
                detected_at=now - timedelta(minutes=(i * 20) + 10),
            )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "unusual_activity",
                "activity_type": "cooking",
                "activity_count": 5,
                "within_minutes": 60,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_unusual_activity_missing_fields(self, db_factory):
        """Should return False when activity_type or activity_count is missing."""
        db = db_factory()
        now = datetime.now(UTC)

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "unusual_activity",
                "activity_count": 5,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "unusual_activity",
                "activity_type": "bathroom",
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()


class TestSceneTrendNoRecentActivity:
    """Tests for no_recent_activity trend detection."""

    def test_no_recent_activity_detected(self, db_factory):
        """Should detect when person has no activity in window."""
        db = db_factory()
        now = datetime.now(UTC)

        # Create old activity (2 hours ago)
        _make_activity(
            db,
            person_id="person123",
            detected_at=now - timedelta(hours=2),
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
                "within_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is True
        db.close()

    def test_no_recent_activity_not_detected(self, db_factory):
        """Should not detect when person has recent activity."""
        db = db_factory()
        now = datetime.now(UTC)

        _make_activity(
            db,
            person_id="person123",
            detected_at=now - timedelta(minutes=5),
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
                "within_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_no_recent_activity_checks_location_history(self, db_factory):
        """Should also check location history, not just activities."""
        db = db_factory()
        now = datetime.now(UTC)

        # Create old activity but recent location
        _make_activity(
            db,
            person_id="person123",
            detected_at=now - timedelta(hours=2),
        )
        _make_location_entry(
            db,
            person_id="person123",
            entered_at=now - timedelta(minutes=5),
            exited_at=now - timedelta(minutes=3),
        )
        db.commit()

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
                "within_minutes": 30,
            },
            sensor=None,
            now=now,
            db=db,
        )
        # Should be False because location history has recent entry
        assert result is False
        db.close()


class TestSceneTrendValidation:
    """Tests for config validation."""

    def test_missing_person_id(self, db_factory):
        """Should return False when person_id is missing."""
        db = db_factory()
        now = datetime.now(UTC)

        result = FILTER.evaluate(
            config={
                "trend_type": "no_recent_activity",
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_missing_trend_type(self, db_factory):
        """Should return False when trend_type is missing."""
        db = db_factory()
        now = datetime.now(UTC)

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_unknown_trend_type(self, db_factory):
        """Should return False for unknown trend_type."""
        db = db_factory()
        now = datetime.now(UTC)

        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "nonexistent_trend",
            },
            sensor=None,
            now=now,
            db=db,
        )
        assert result is False
        db.close()

    def test_no_db_session(self, db_factory):
        """Should return False when db is None."""
        result = FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
            },
            sensor=None,
            now=datetime.now(UTC),
            db=None,
        )
        assert result is False
