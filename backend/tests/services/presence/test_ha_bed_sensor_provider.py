"""Tests for HaBedSensorProvider."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.services.presence.providers.ha_bed_sensor import (
    HaBedSensorProvider,
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
        # Create a simple object with the expected attributes.
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


async def test_cache_empty_returns_none():
    """Cache empty → None."""
    cache = _StubHaStateCache()
    provider = HaBedSensorProvider(
        cache=cache,
        entity_id="binary_sensor.bed",
        person_id="mom",
        room_id="bedroom",
        room_name="Master Bedroom",
    )
    at = datetime.now(UTC)
    result = await provider.probe("mom", at)
    assert result is None


async def test_cache_sensor_off_returns_none():
    """Cache has bed sensor off → None."""
    now = datetime.now(UTC)
    cache = _StubHaStateCache()
    cache.set_state("binary_sensor.bed", "off", now)

    provider = HaBedSensorProvider(
        cache=cache,
        entity_id="binary_sensor.bed",
        person_id="mom",
        room_id="bedroom",
        room_name="Master Bedroom",
    )
    result = await provider.probe("mom", now)
    assert result is None


async def test_cache_sensor_on_returns_snapshot():
    """Cache has bed sensor on → snapshot with right room and confidence."""
    now = datetime.now(UTC)
    cache = _StubHaStateCache()
    cache.set_state("binary_sensor.bed", "on", now)

    provider = HaBedSensorProvider(
        cache=cache,
        entity_id="binary_sensor.bed",
        person_id="mom",
        room_id="bedroom",
        room_name="Master Bedroom",
        confidence=0.95,
    )
    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status.value == "present_room"
    assert result.room_id == "bedroom"
    assert result.room_name == "Master Bedroom"
    assert result.confidence == 0.95
    assert "bed sensor" in result.notes


async def test_wrong_person_id_returns_none():
    """Wrong person_id → None."""
    now = datetime.now(UTC)
    cache = _StubHaStateCache()
    cache.set_state("binary_sensor.bed", "on", now)

    provider = HaBedSensorProvider(
        cache=cache,
        entity_id="binary_sensor.bed",
        person_id="mom",
        room_id="bedroom",
        room_name="Master Bedroom",
    )
    result = await provider.probe("dad", now)
    assert result is None
