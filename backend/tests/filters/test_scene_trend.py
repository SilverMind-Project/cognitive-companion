"""Tests for SceneTrendFilter - scene trend context filter (R2: PersonLocationService SSOT).

Location-based trends (prolonged_stay, frequent_visits, no_recent_activity)
use mock PersonLocationService.presence_history().
Activity-based trends (unusual_activity) still use DB (PersonActivity table).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.filters.builtin.scene_trend import SceneTrendFilter
from backend.services.person_location.types import PresenceSegment


def _seg(
    room_id: int,
    room_name: str = "bedroom",
    entered_at: datetime | None = None,
    exited_at: datetime | None = None,
    person_id: str = "person123",
) -> PresenceSegment:
    """Create a PresenceSegment fixture."""
    return PresenceSegment(
        id=uuid4(),
        person_id=person_id,
        room_id=room_id,
        entered_at=entered_at or datetime.now(UTC),
        exited_at=exited_at,
        entry_source="observed",
        confidence=0.9,
        last_observed_at=entered_at or datetime.now(UTC),
        metadata={"room_name": room_name},
    )


def _services(*segments: PresenceSegment):
    """Build mock services container with presence_history()."""
    svc = MagicMock()
    svc.presence_history = AsyncMock(return_value=list(segments))
    services = MagicMock()
    services.person_location = svc
    return services


def _ensure_person(db, person_id="person123"):
    """Ensure a HouseholdMember exists in the DB."""
    from backend.models.person import HouseholdMember

    person = db.get(HouseholdMember, person_id)
    if not person:
        person = HouseholdMember(id=person_id, name="Test Person", is_active=True)
        db.add(person)
        db.flush()


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


# ---------------------------------------------------------------------------
# prolonged_stay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSceneTrendProlongedStay:
    async def test_prolonged_stay_detected(self):
        """Should detect when person stayed in room > threshold."""
        now = datetime.now(UTC)
        seg = _seg(
            room_id=1, room_name="bedroom",
            entered_at=now - timedelta(minutes=60),
            exited_at=None,  # still there
        )
        svc = _services(seg)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "threshold_minutes": 30,
            },
            sensor=None, now=now, services=svc,
        )
        assert result is True

    async def test_prolonged_stay_not_detected(self):
        """Should not detect when stay is below threshold."""
        now = datetime.now(UTC)
        seg = _seg(
            room_id=1, room_name="bedroom",
            entered_at=now - timedelta(minutes=20),
            exited_at=now - timedelta(minutes=10),
        )
        svc = _services(seg)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "threshold_minutes": 30,
            },
            sensor=None, now=now, services=svc,
        )
        assert result is False

    async def test_prolonged_stay_filtered_by_room(self):
        """Should respect room_name filter for prolonged stay."""
        now = datetime.now(UTC)
        s1 = _seg(room_id=1, room_name="kitchen",
                   entered_at=now - timedelta(minutes=60),
                   exited_at=None)
        s2 = _seg(room_id=2, room_name="bedroom",
                   entered_at=now - timedelta(minutes=15),
                   exited_at=now - timedelta(minutes=5))
        svc = _services(s1, s2)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "room_name": "bedroom",
                "threshold_minutes": 30,
            },
            sensor=None, now=now, services=svc,
        )
        assert result is False

        result2 = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "room_name": "kitchen",
                "threshold_minutes": 30,
            },
            sensor=None, now=now, services=svc,
        )
        assert result2 is True

    async def test_prolonged_stay_missing_threshold(self):
        """Should return False when threshold_minutes is not provided."""
        now = datetime.now(UTC)
        seg = _seg(room_id=1, room_name="bedroom",
                    entered_at=now - timedelta(minutes=60),
                    exited_at=None)
        svc = _services(seg)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
            },
            sensor=None, now=now, services=svc,
        )
        assert result is False

    async def test_fail_closed_no_person_location(self):
        """When services.person_location is None, fail closed."""
        now = datetime.now(UTC)
        services = MagicMock()
        services.person_location = None
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "threshold_minutes": 30,
            },
            sensor=None, now=now, services=services,
        )
        assert result is False


# ---------------------------------------------------------------------------
# frequent_visits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSceneTrendFrequentVisits:
    async def test_frequent_visits_detected(self):
        """Should detect when person visited room >= visit_count times."""
        now = datetime.now(UTC)
        segments = []
        for i in range(6):
            segments.append(_seg(
                room_id=1, room_name="bathroom",
                entered_at=now - timedelta(minutes=(i * 10) + 5),
                exited_at=now - timedelta(minutes=i * 10),
            ))
        svc = _services(*segments)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "frequent_visits",
                "room_name": "bathroom",
                "visit_count": 5,
                "within_minutes": 60,
            },
            sensor=None, now=now, services=svc,
        )
        assert result is True

    async def test_frequent_visits_not_detected(self):
        """Should not detect when visits are below threshold."""
        now = datetime.now(UTC)
        segments = []
        for i in range(3):
            segments.append(_seg(
                room_id=1, room_name="bathroom",
                entered_at=now - timedelta(minutes=(i * 15) + 5),
                exited_at=now - timedelta(minutes=i * 15),
            ))
        svc = _services(*segments)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "frequent_visits",
                "room_name": "bathroom",
                "visit_count": 5,
                "within_minutes": 60,
            },
            sensor=None, now=now, services=svc,
        )
        assert result is False

    async def test_frequent_visits_without_room_filter(self):
        """Should count visits across all rooms when no room_name filter."""
        now = datetime.now(UTC)
        segments = []
        for i in range(4):
            segments.append(_seg(
                room_id=1, room_name="bedroom",
                entered_at=now - timedelta(minutes=(i * 10) + 5),
                exited_at=now - timedelta(minutes=i * 10),
            ))
            segments.append(_seg(
                room_id=2, room_name="kitchen",
                entered_at=now - timedelta(minutes=(i * 10) + 8),
                exited_at=now - timedelta(minutes=i * 10 + 3),
            ))
        svc = _services(*segments)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "frequent_visits",
                "visit_count": 5,
                "within_minutes": 60,
            },
            sensor=None, now=now, services=svc,
        )
        assert result is True


# ---------------------------------------------------------------------------
# unusual_activity (still uses DB via PersonActivity)
# ---------------------------------------------------------------------------


class TestSceneTrendUnusualActivity:
    @pytest.mark.asyncio
    async def test_unusual_activity_detected(self, db_factory):
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

        result = await FILTER.evaluate(
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

    @pytest.mark.asyncio
    async def test_unusual_activity_not_detected(self, db_factory):
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

        result = await FILTER.evaluate(
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

    @pytest.mark.asyncio
    async def test_unusual_activity_missing_fields(self, db_factory):
        """Should return False when activity_type or activity_count is missing."""
        db = db_factory()
        now = datetime.now(UTC)

        result = await FILTER.evaluate(
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

        result = await FILTER.evaluate(
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


# ---------------------------------------------------------------------------
# no_recent_activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSceneTrendNoRecentActivity:
    async def test_no_recent_activity_detected(self, db_factory):
        """Should detect when person has no activity in window."""
        db = db_factory()
        now = datetime.now(UTC)
        # No segments returned by presence_history.
        svc = _services()
        # Create old activity (2 hours ago)
        _make_activity(
            db,
            person_id="person123",
            detected_at=now - timedelta(hours=2),
        )
        db.commit()

        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
                "within_minutes": 30,
            },
            sensor=None, now=now, db=db, services=svc,
        )
        assert result is True
        db.close()

    async def test_no_recent_activity_with_recent_location(self, db_factory):
        """Should not detect when person has recent location."""
        db = db_factory()
        now = datetime.now(UTC)
        seg = _seg(room_id=1, room_name="kitchen",
                    entered_at=now - timedelta(minutes=5))
        svc = _services(seg)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
                "within_minutes": 30,
            },
            sensor=None, now=now, db=db, services=svc,
        )
        assert result is False
        db.close()

    async def test_no_recent_activity_with_recent_activity(self, db_factory):
        """Should not detect when person has recent activity (even without location)."""
        db = db_factory()
        now = datetime.now(UTC)
        svc = _services()  # no location segments
        _make_activity(
            db,
            person_id="person123",
            detected_at=now - timedelta(minutes=5),
        )
        db.commit()

        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "no_recent_activity",
                "within_minutes": 30,
            },
            sensor=None, now=now, db=db, services=svc,
        )
        assert result is False
        db.close()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSceneTrendValidation:
    @pytest.mark.asyncio
    async def test_missing_person_id(self, db_factory):
        """Should return False when person_id is missing."""
        db = db_factory()
        now = datetime.now(UTC)
        result = await FILTER.evaluate(
            config={"trend_type": "no_recent_activity"},
            sensor=None, now=now, db=db,
        )
        assert result is False
        db.close()

    @pytest.mark.asyncio
    async def test_missing_trend_type(self, db_factory):
        """Should return False when trend_type is missing."""
        db = db_factory()
        now = datetime.now(UTC)
        result = await FILTER.evaluate(
            config={"person_id": "person123"},
            sensor=None, now=now, db=db,
        )
        assert result is False
        db.close()

    @pytest.mark.asyncio
    async def test_unknown_trend_type(self, db_factory):
        """Should return False for unknown trend type."""
        db = db_factory()
        now = datetime.now(UTC)
        result = await FILTER.evaluate(
            config={"person_id": "person123", "trend_type": "nonexistent"},
            sensor=None, now=now, db=db,
        )
        assert result is False
        db.close()

    @pytest.mark.asyncio
    async def test_no_db_session_for_unusual_activity(self):
        """unusual_activity without db returns False."""
        now = datetime.now(UTC)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "unusual_activity",
                "activity_type": "bathroom",
                "activity_count": 5,
            },
            sensor=None, now=now, db=None,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_services_for_location_trend(self):
        """location-based trend without services fails closed."""
        now = datetime.now(UTC)
        result = await FILTER.evaluate(
            config={
                "person_id": "person123",
                "trend_type": "prolonged_stay",
                "threshold_minutes": 30,
            },
            sensor=None, now=now, services=None,
        )
        assert result is False
