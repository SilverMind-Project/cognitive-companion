"""Unit tests for :class:`PresenceDwellFilter`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.filters.builtin.presence_dwell import PresenceDwellFilter
from backend.services.presence import PresenceSnapshot, PresenceSource, PresenceStatus


class _StubPresenceService:
    def __init__(self, snapshot: PresenceSnapshot) -> None:
        self.snapshot = snapshot

    async def get(self, person_id: str, *, at=None):
        return self.snapshot


def _make_snapshot(
    status: PresenceStatus,
    dwell_minutes: float | None = 15.0,
) -> PresenceSnapshot:
    return PresenceSnapshot(
        person_id="mom",
        status=status,
        room_id="k1",
        room_name="kitchen",
        confidence=0.9,
        last_seen_at=datetime.now(UTC),
        dwell_minutes=dwell_minutes,
        sources=(PresenceSource(name="cts_location", confidence=0.9),),
        inferred_at=datetime.now(UTC),
    )


@pytest.fixture
def now():
    return datetime.now(UTC)


def test_match_dwell_above_threshold(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, dwell_minutes=20.0)
    filter_instance = PresenceDwellFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "min_minutes": 15},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_no_match_dwell_below_threshold(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, dwell_minutes=3.0)
    filter_instance = PresenceDwellFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "min_minutes": 10},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


def test_status_filter_matches(now):
    snapshot = _make_snapshot(PresenceStatus.ASLEEP, dwell_minutes=120.0)
    filter_instance = PresenceDwellFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "asleep", "min_minutes": 60},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_status_filter_no_match(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, dwell_minutes=120.0)
    filter_instance = PresenceDwellFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "asleep", "min_minutes": 60},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


def test_no_dwell_returns_false(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, dwell_minutes=None)
    filter_instance = PresenceDwellFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "min_minutes": 5},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


def test_no_person_returns_false(now):
    filter_instance = PresenceDwellFilter()
    services = type("Svc", (), {"presence": None})()
    result = filter_instance.evaluate(
        config={"min_minutes": 5},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False
