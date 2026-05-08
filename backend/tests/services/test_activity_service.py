"""Tests for ActivityService - domain service consolidation.

Uses the in-memory DB fixture (db_factory) for session tests, and mocks
for record/query tests that need PersonTrackingService.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.activity import ActivityService
from backend.services.activity.types import ActivityRecord, SessionRecord
from backend.services.activity_session import ActivitySessionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_person(db, person_id="person123"):
    """Create a HouseholdMember in the test DB."""
    from backend.models.person import HouseholdMember

    member = HouseholdMember(id=person_id, name="Test Person", is_active=True)
    db.add(member)
    db.flush()
    return member


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def activity_session(db_factory):
    """ActivitySessionService backed by the test DB."""
    return ActivitySessionService(db_session_factory=db_factory)


@pytest.fixture
def activity_service(activity_session):
    """ActivityService delegating to activity_session (person_tracking mocked)."""
    mock_pt = MagicMock()
    return ActivityService(
        person_tracking=mock_pt,
        activity_session=activity_session,
    )


# ---------------------------------------------------------------------------
# Tests: record()
# ---------------------------------------------------------------------------


class TestRecord:
    """ActivityService.record() delegation tests."""

    @pytest.mark.asyncio
    async def test_record_delegates_and_maps_result(self, activity_service):
        """Should delegate to person_tracking.record_activity and return ActivityRecord."""
        # Arrange: mock record_activity to return a PersonActivity-like object
        mock_orm = MagicMock()
        mock_orm.id = 42
        mock_orm.person_id = "person123"
        mock_orm.activity_type = "bathroom"
        mock_orm.room_id = 5
        mock_orm.room_name = "bathroom"
        mock_orm.confidence = 0.85
        mock_orm.source_event_id = 1
        mock_orm.metadata_json = {"note": "test"}
        mock_orm.duration_minutes = None
        mock_orm.session_id = None
        mock_orm.detected_at = datetime.now(UTC)

        activity_service._person_tracking.record_activity = AsyncMock(return_value=mock_orm)

        # Act
        record = await activity_service.record(
            person_id="person123",
            activity_type="bathroom",
            room_name="bathroom",
            confidence=0.85,
            source_event_id=1,
            metadata={"note": "test"},
        )

        # Assert
        assert isinstance(record, ActivityRecord)
        assert record.id == 42
        assert record.person_id == "person123"
        assert record.activity_type == "bathroom"
        assert record.room_name == "bathroom"
        assert record.confidence == 0.85
        assert record.metadata_json == {"note": "test"}
        activity_service._person_tracking.record_activity.assert_awaited_once_with(
            person_id="person123",
            activity_type="bathroom",
            room_name="bathroom",
            confidence=0.85,
            source_event_id=1,
            metadata={"note": "test"},
        )

    @pytest.mark.asyncio
    async def test_record_handles_none_metadata(self, activity_service):
        """Should pass None metadata through correctly."""
        mock_orm = MagicMock()
        mock_orm.id = 1
        mock_orm.person_id = "p1"
        mock_orm.activity_type = "sleep"
        mock_orm.room_id = None
        mock_orm.room_name = "bedroom"
        mock_orm.confidence = 0.9
        mock_orm.source_event_id = None
        mock_orm.metadata_json = None
        mock_orm.duration_minutes = None
        mock_orm.session_id = None
        mock_orm.detected_at = datetime.now(UTC)

        activity_service._person_tracking.record_activity = AsyncMock(return_value=mock_orm)

        record = await activity_service.record(
            person_id="p1",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.9,
        )

        assert record.metadata_json is None

    @pytest.mark.asyncio
    async def test_record_propagates_exception(self, activity_service, monkeypatch):
        """Should re-raise exceptions from person_tracking.record_activity."""
        async def _fail(*args, **kwargs):
            raise RuntimeError("DB error")

        activity_service._person_tracking.record_activity = _fail

        with pytest.raises(RuntimeError, match="DB error"):
            await activity_service.record(
                person_id="x",
                activity_type="other",
                room_name="nowhere",
                confidence=0.1,
            )


# ---------------------------------------------------------------------------
# Tests: open_session()
# ---------------------------------------------------------------------------


class TestOpenSession:
    """ActivityService.open_session() delegation tests."""

    def test_open_session_creates(self, activity_service):
        """Should delegate to activity_session.open_session and return SessionRecord."""
        started_at = datetime.now(UTC)
        result = activity_service.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        assert isinstance(result, SessionRecord)
        assert result.session_id.startswith("person123_sleep_")
        assert result.person_id == "person123"
        assert result.activity_type == "sleep"
        assert result.room_name == "bedroom"
        assert result.opened_at == started_at
        assert result.timeout_minutes == 720  # sleep default
        assert result.status == "open"
        assert result.closed_at is None
        assert result.duration_minutes is None
        assert result.was_existing is False

    def test_open_session_reuses_existing(self, activity_session):
        """Should return existing open session (idempotent)."""
        started_at = datetime.now(UTC)

        first = activity_session.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )
        second = activity_session.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        assert first.session_id == second.session_id
        assert first.was_existing is False
        assert second.was_existing is True

    def test_open_session_with_timeout(self, activity_service):
        """Should pass timeout_minutes through."""
        started_at = datetime.now(UTC)
        result = activity_service.open_session(
            person_id="person123",
            activity_type="bathroom",
            room_name="bathroom",
            confidence=0.8,
            started_at=started_at,
            timeout_minutes=45,
        )

        assert result.timeout_minutes == 45


# ---------------------------------------------------------------------------
# Tests: close_session()
# ---------------------------------------------------------------------------


class TestCloseSession:
    """ActivityService.close_session() delegation tests."""

    def test_close_session_computes_duration(self, db_engine):
        """Should delegate to activity_session.close_session and return SessionRecord."""
        from sqlalchemy.orm import sessionmaker

        from backend.services.activity_session import ActivitySessionService

        factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

        def _make():
            return factory()

        sess_svc = ActivitySessionService(db_session_factory=_make)

        started_at = datetime.now(UTC) - timedelta(minutes=30)

        sess_svc.open_session(
            person_id="person123",
            activity_type="sleep",
            room_name="bedroom",
            confidence=0.95,
            started_at=started_at,
            start_event_id=None,
        )

        ended_at = datetime.now(UTC)

        # Wrap in ActivityService to verify the mapping
        mock_pt = MagicMock()
        svc = ActivityService(person_tracking=mock_pt, activity_session=sess_svc)
        mapped = svc.close_session(
            person_id="person123",
            activity_type="sleep",
            ended_at=ended_at,
            end_event_id=None,
        )

        assert isinstance(mapped, SessionRecord)
        assert mapped.session_id.startswith("person123_sleep_")
        assert mapped.person_id == "person123"
        assert mapped.activity_type == "sleep"
        assert mapped.closed_at == ended_at
        assert mapped.status == "closed"
        assert mapped.closed_via == "explicit"
        assert mapped.duration_minutes is not None
        assert mapped.duration_minutes >= 30

    def test_close_session_nonexistent_raises(self, activity_service):
        """Should propagate ValueError when no open session exists."""
        with pytest.raises(ValueError, match="No open session"):
            activity_service.close_session(
                person_id="nonexistent",
                activity_type="sleep",
                ended_at=datetime.now(UTC),
            )


# ---------------------------------------------------------------------------
# Tests: query_recent()
# ---------------------------------------------------------------------------


class TestQueryRecent:
    """ActivityService.query_recent() delegation tests."""

    @pytest.mark.asyncio
    async def test_query_recent_delegates_and_maps(self, activity_service):
        """Should delegate to person_tracking.get_recent_activities and return ActivityRecords."""
        mock_rows = [
            {
                "id": 1,
                "person_id": "person123",
                "activity_type": "bathroom",
                "room_name": "bathroom",
                "confidence": 0.9,
                "detected_at": datetime.now(UTC).isoformat(),
            },
            {
                "id": 2,
                "person_id": "person123",
                "activity_type": "meal_eating",
                "room_name": "kitchen",
                "confidence": 0.8,
                "detected_at": datetime.now(UTC).isoformat(),
            },
        ]
        activity_service._person_tracking.get_recent_activities = AsyncMock(return_value=mock_rows)

        since = datetime.now(UTC) - timedelta(minutes=5)
        records = await activity_service.query_recent(
            person_id="person123",
            since=since,
        )

        assert len(records) == 2
        assert all(isinstance(r, ActivityRecord) for r in records)
        types = {r.activity_type for r in records}
        assert types == {"bathroom", "meal_eating"}
        activity_service._person_tracking.get_recent_activities.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_recent_empty(self, activity_service):
        """Should return empty list when no activities exist."""
        activity_service._person_tracking.get_recent_activities = AsyncMock(return_value=[])

        since = datetime.now(UTC) - timedelta(minutes=60)
        records = await activity_service.query_recent(
            person_id="nonexistent",
            since=since,
        )

        assert records == []
