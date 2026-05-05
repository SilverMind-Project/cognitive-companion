"""Tests for HaDeviceTrackerProvider."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.services.presence.providers.ha_device_tracker import (
    HaDeviceTrackerProvider,
)


class _StubHaStateCache:
    """Minimal fake HaStateCache for unit tests."""

    def __init__(self) -> None:
        self._states: dict[str, object] = {}
        self._registered: set[str] = set()

    def get(self, entity_id: str):
        return self._states.get(entity_id)

    def register(self, entity_id: str) -> None:
        self._registered.add(entity_id)

    def set_state(self, entity_id: str, state: str, last_changed) -> None:
        self._states[entity_id] = type(
            "HaState",
            (),
            {
                "entity_id": entity_id,
                "state": state,
                "attributes": {},
                "last_changed": last_changed,
            },
        )()


def _make_provider(**overrides):
    """Create a default HaDeviceTrackerProvider with optional overrides."""
    defaults = {
        "cache": _StubHaStateCache(),
        "entity_id_template": "device_tracker.{person_id}_phone",
        "confidence": 0.8,
    }
    defaults.update(overrides)
    return HaDeviceTrackerProvider(**defaults)


async def test_home_returns_present_home():
    """Device tracker state=home → PRESENT_HOME."""
    now = datetime.now(UTC)
    provider = _make_provider()
    provider._cache.set_state("device_tracker.mom_phone", "home", now)

    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status.value == "present_home"
    assert result.room_id is None


async def test_away_returns_away():
    """Device tracker state=away → AWAY."""
    now = datetime.now(UTC)
    provider = _make_provider()
    provider._cache.set_state("device_tracker.mom_phone", "away", now)

    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status.value == "away"


async def test_unknown_zone_returns_present_home_with_notes():
    """Named zone state → PRESENT_HOME with zone notes."""
    now = datetime.now(UTC)
    provider = _make_provider()
    provider._cache.set_state("device_tracker.mom_phone", "work", now)

    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status.value == "present_home"
    assert result.notes == "zone=work"


async def test_not_home_returns_away():
    """Device tracker state=not_home → AWAY."""
    now = datetime.now(UTC)
    provider = _make_provider()
    provider._cache.set_state("device_tracker.mom_phone", "not_home", now)

    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status.value == "away"


async def test_cache_miss_returns_none():
    """No cached state → None."""
    now = datetime.now(UTC)
    provider = _make_provider()

    result = await provider.probe("mom", now)
    assert result is None


async def test_person_id_map_override():
    """person_id_map changes entity resolution."""
    now = datetime.now(UTC)
    provider = _make_provider(
        person_id_map={"mom": "mom_phone_v2"},
    )
    # _resolve_entity_id("mom") → "device_tracker.mom_phone_v2_phone"
    provider._cache.set_state("device_tracker.mom_phone_v2_phone", "home", now)

    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status.value == "present_home"


async def test_register_for_person():
    """register_for_person() adds entity to cache registration set."""
    provider = _make_provider()
    provider.register_for_person("mom")
    assert "device_tracker.mom_phone" in provider._cache._registered
