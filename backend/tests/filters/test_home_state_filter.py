"""Unit tests for :class:`HomeStateFilter`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.filters.builtin.home_state import HomeStateFilter
from backend.services.presence import PresenceSnapshot, PresenceSource, PresenceStatus


class _StubPresenceService:
    def __init__(self, snapshot: PresenceSnapshot) -> None:
        self.snapshot = snapshot

    async def get(self, person_id: str, *, at=None):
        return self.snapshot


def _make_snapshot(status: PresenceStatus) -> PresenceSnapshot:
    return PresenceSnapshot(
        person_id="mom",
        status=status,
        room_id="k1",
        room_name="kitchen",
        confidence=0.9,
        last_seen_at=datetime.now(UTC),
        dwell_minutes=10.0,
        sources=(PresenceSource(name="cts_location", confidence=0.9),),
        inferred_at=datetime.now(UTC),
    )


@pytest.fixture
def now():
    return datetime.now(UTC)


def test_at_home_present_room(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM)
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "state": "at_home"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_at_home_asleep(now):
    snapshot = _make_snapshot(PresenceStatus.ASLEEP)
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "state": "at_home"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_asleep(now):
    snapshot = _make_snapshot(PresenceStatus.ASLEEP)
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "state": "asleep"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_away(now):
    snapshot = _make_snapshot(PresenceStatus.AWAY)
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "state": "away"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_unknown(now):
    snapshot = _make_snapshot(PresenceStatus.UNKNOWN)
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "state": "unknown"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_stale_is_unknown(now):
    snapshot = _make_snapshot(PresenceStatus.STALE)
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "state": "unknown"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_no_person_returns_false(now):
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": None})()
    result = filter_instance.evaluate(
        config={"state": "at_home"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False
