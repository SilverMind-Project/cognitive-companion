"""Tests for HaStateCache."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.integrations.ha_state_cache import HaStateCache
from backend.integrations.homeassistant import HaStateEvent
from backend.services.presence.providers.ha_bed_sensor import HaBedSensorProvider


class _FakeHaClient:
    """Fake HomeAssistantClient that delivers canned events."""

    def __init__(self, events: list[HaStateEvent] | None = None) -> None:
        self.configured = True
        self._events = events or []
        self._on_callback = None
        self._opened = False

    async def open_event_subscription(
        self,
        entity_ids,
        on_state_changed,
    ):
        self._opened = True
        self._on_callback = on_state_changed
        # Deliver all canned events synchronously before returning.
        for event in self._events:
            await on_state_changed(event)
        # Return a no-op context manager.
        return _NoopSubscription()


class _NoopSubscription:
    """No-op async context manager for the fake client."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def test_cache_populated_by_events():
    """After start() with events, cache.get returns correct state."""
    now = datetime.now(UTC)
    events = [
        HaStateEvent(
            entity_id="binary_sensor.bed_occupancy",
            state="on",
            attributes={"friendly_name": "Bed"},
            fired_at=now,
        ),
    ]
    client = _FakeHaClient(events)
    cache = HaStateCache(client)
    cache.register("binary_sensor.bed_occupancy")
    await cache.start()

    state = cache.get("binary_sensor.bed_occupancy")
    assert state is not None
    assert state.state == "on"
    assert state.attributes == {"friendly_name": "Bed"}


async def test_cache_history_newest_first():
    """History returns events newest-first with correct truncation."""
    now = datetime.now(UTC)
    events = [
        HaStateEvent(
            entity_id="binary_sensor.motion",
            state="off",
            attributes={},
            fired_at=now,
        ),
        HaStateEvent(
            entity_id="binary_sensor.motion",
            state="on",
            attributes={},
            fired_at=now,
        ),
    ]
    client = _FakeHaClient(events)
    cache = HaStateCache(client)
    cache.register("binary_sensor.motion")
    await cache.start()

    hist = cache.history("binary_sensor.motion")
    assert len(hist) == 2
    assert hist[0].state == "on"   # newest
    assert hist[1].state == "off"  # oldest


async def test_register_after_start():
    """register() after start() adds entity to subscription set."""
    client = _FakeHaClient()
    cache = HaStateCache(client)
    await cache.start()
    cache.register("binary_sensor.kitchen_motion")

    # The entity was not in the canned events, so it should not be in cache.
    assert cache.get("binary_sensor.kitchen_motion") is None


async def test_get_unknown_entity():
    """get(unknown_entity) returns None."""
    client = _FakeHaClient()
    cache = HaStateCache(client)
    await cache.start()

    assert cache.get("binary_sensor.nonexistent") is None


async def test_history_empty_for_unknown():
    """history(unknown) returns empty tuple."""
    client = _FakeHaClient()
    cache = HaStateCache(client)
    await cache.start()

    assert cache.history("binary_sensor.nonexistent") == ()


async def test_cache_with_bed_sensor_provider():
    """HaBedSensorProvider reads from cache and returns snapshot."""
    now = datetime.now(UTC)
    events = [
        HaStateEvent(
            entity_id="binary_sensor.bed_occupancy",
            state="on",
            attributes={},
            fired_at=now,
        ),
    ]
    client = _FakeHaClient(events)
    cache = HaStateCache(client)
    cache.register("binary_sensor.bed_occupancy")
    await cache.start()

    provider = HaBedSensorProvider(
        cache=cache,
        entity_id="binary_sensor.bed_occupancy",
        person_id="mom",
        room_id="bedroom",
        room_name="Master Bedroom",
    )
    provider.register()

    snapshot = await provider.probe("mom", now)
    assert snapshot is not None
    assert snapshot.status.value == "present_room"
    assert snapshot.room_id == "bedroom"
    assert snapshot.confidence == 0.95


async def test_cache_clears_on_stop():
    """stop() clears the cache."""
    now = datetime.now(UTC)
    events = [
        HaStateEvent(
            entity_id="binary_sensor.bed_occupancy",
            state="on",
            attributes={},
            fired_at=now,
        ),
    ]
    client = _FakeHaClient(events)
    cache = HaStateCache(client)
    cache.register("binary_sensor.bed_occupancy")
    await cache.start()
    assert cache.get("binary_sensor.bed_occupancy") is not None

    await cache.stop()
    assert cache.get("binary_sensor.bed_occupancy") is None
