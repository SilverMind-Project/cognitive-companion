"""Unit tests for :class:`PresenceStatusFilter`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.filters.builtin.presence_status import PresenceStatusFilter
from backend.services.presence import PresenceSnapshot, PresenceSource, PresenceStatus


class _StubPresenceService:
    def __init__(self, snapshot: PresenceSnapshot) -> None:
        self.snapshot = snapshot

    async def get(self, person_id: str, *, at=None):
        return self.snapshot


def _make_snapshot(status: PresenceStatus, room_name: str | None = "kitchen") -> PresenceSnapshot:
    return PresenceSnapshot(
        person_id="mom",
        status=status,
        room_id="k1",
        room_name=room_name,
        confidence=0.9,
        last_seen_at=datetime.now(UTC),
        dwell_minutes=10.0,
        sources=(PresenceSource(name="cts_location", confidence=0.9),),
        inferred_at=datetime.now(UTC),
    )


@pytest.fixture
def now():
    return datetime.now(UTC)


def test_match_present_room(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM)
    filter_instance = PresenceStatusFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "present_room"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_no_match_wrong_status(now):
    snapshot = _make_snapshot(PresenceStatus.AWAY)
    filter_instance = PresenceStatusFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "present_room"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


def test_no_person_returns_false(now):
    filter_instance = PresenceStatusFilter()
    services = type("Svc", (), {"presence": None})()
    result = filter_instance.evaluate(
        config={"status": "present_room"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


def test_room_filter_matches(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, room_name="kitchen")
    filter_instance = PresenceStatusFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "present_room", "room_name": "kitchen"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


def test_room_filter_no_match(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM, room_name="kitchen")
    filter_instance = PresenceStatusFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "present_room", "room_name": "bedroom"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


def test_asleep_status(now):
    snapshot = _make_snapshot(PresenceStatus.ASLEEP, room_name="bedroom")
    filter_instance = PresenceStatusFilter()
    services = type("Svc", (), {"presence": _StubPresenceService(snapshot)})()
    result = filter_instance.evaluate(
        config={"person_id": "mom", "status": "asleep"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True
