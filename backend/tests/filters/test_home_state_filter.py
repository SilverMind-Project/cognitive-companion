"""Unit tests for :class:`HomeStateFilter` (WTR7: async evaluate)."""

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
        sources=(PresenceSource(name="location_service", confidence=0.9),),
        inferred_at=datetime.now(UTC),
    )


@pytest.fixture
def now():
    return datetime.now(UTC)


@pytest.mark.asyncio
async def test_at_home_present_room(now):
    snapshot = _make_snapshot(PresenceStatus.PRESENT_ROOM)
    filter_instance = HomeStateFilter()
    services = type(
        "Svc", (), {"presence": _StubPresenceService(snapshot), "person_location": None}
    )()
    result = await filter_instance.evaluate(
        config={"person_id": "mom", "state": "at_home"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_at_home_asleep(now):
    snapshot = _make_snapshot(PresenceStatus.ASLEEP)
    filter_instance = HomeStateFilter()
    services = type(
        "Svc", (), {"presence": _StubPresenceService(snapshot), "person_location": None}
    )()
    result = await filter_instance.evaluate(
        config={"person_id": "mom", "state": "at_home"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_asleep(now):
    snapshot = _make_snapshot(PresenceStatus.ASLEEP)
    filter_instance = HomeStateFilter()
    services = type(
        "Svc", (), {"presence": _StubPresenceService(snapshot), "person_location": None}
    )()
    result = await filter_instance.evaluate(
        config={"person_id": "mom", "state": "asleep"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_away(now):
    snapshot = _make_snapshot(PresenceStatus.AWAY)
    filter_instance = HomeStateFilter()
    services = type(
        "Svc", (), {"presence": _StubPresenceService(snapshot), "person_location": None}
    )()
    result = await filter_instance.evaluate(
        config={"person_id": "mom", "state": "away"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_unknown(now):
    snapshot = _make_snapshot(PresenceStatus.UNKNOWN)
    filter_instance = HomeStateFilter()
    services = type(
        "Svc", (), {"presence": _StubPresenceService(snapshot), "person_location": None}
    )()
    result = await filter_instance.evaluate(
        config={"person_id": "mom", "state": "unknown"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_stale_is_unknown(now):
    snapshot = _make_snapshot(PresenceStatus.STALE)
    filter_instance = HomeStateFilter()
    services = type(
        "Svc", (), {"presence": _StubPresenceService(snapshot), "person_location": None}
    )()
    result = await filter_instance.evaluate(
        config={"person_id": "mom", "state": "unknown"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_no_person_returns_false(now):
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"presence": None, "person_location": None})()
    result = await filter_instance.evaluate(
        config={"state": "at_home"},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


class _FakeHaState:
    def __init__(self, state: str) -> None:
        self.state = state


class _StubHaStateCache:
    def __init__(self, states: dict[str, str]) -> None:
        self._states = states

    def get(self, entity_id: str):
        state = self._states.get(entity_id)
        return _FakeHaState(state) if state is not None else None


@pytest.mark.asyncio
async def test_entity_id_matches_states_any(now):
    filter_instance = HomeStateFilter()
    services = type(
        "Svc",
        (),
        {"ha_state_cache": _StubHaStateCache({"media_player.tv": "playing"})},
    )()
    result = await filter_instance.evaluate(
        config={"entity_id": "media_player.tv", "states_any": ["playing", "on"]},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_entity_id_does_not_match_states_any(now):
    filter_instance = HomeStateFilter()
    services = type(
        "Svc",
        (),
        {"ha_state_cache": _StubHaStateCache({"media_player.tv": "off"})},
    )()
    result = await filter_instance.evaluate(
        config={"entity_id": "media_player.tv", "states_any": ["playing", "on"]},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


@pytest.mark.asyncio
async def test_entity_id_no_cache_service_fails_closed(now):
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"ha_state_cache": None})()
    result = await filter_instance.evaluate(
        config={"entity_id": "media_player.tv", "states_any": ["playing"]},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False


@pytest.mark.asyncio
async def test_entity_id_cache_miss_fails_closed(now):
    filter_instance = HomeStateFilter()
    services = type("Svc", (), {"ha_state_cache": _StubHaStateCache({})})()
    result = await filter_instance.evaluate(
        config={"entity_id": "media_player.tv", "states_any": ["playing"]},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False
