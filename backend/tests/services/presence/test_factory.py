"""Tests for presence provider factory."""

from __future__ import annotations

from backend.services.presence.config import PresenceConfig
from backend.services.presence.factory import (
    build_providers,
    collect_required_entities,
)


class _StubLocationRepository:
    """Minimal stub for LocationRepository."""

    def get_state(self, person_id):
        return None

    def get_open_history_row(self, person_id, room_name=None):
        return None

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _StubHaStateCache:
    """Minimal stub for HaStateCache."""

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


def _make_config(**overrides):
    """Create a default PresenceConfig with optional overrides."""
    defaults = {
        "providers": [
            {
                "name": "cts_location",
                "ttl_seconds": 120,
                "priority": 50,
            },
            {
                "name": "ha_bed_sensor",
                "entity_id": "binary_sensor.bed",
                "person_id": "mom",
                "room_id": "bedroom",
                "room_name": "Master Bedroom",
                "priority": 70,
            },
            {
                "name": "ha_device_tracker",
                "entity_id_template": "device_tracker.{person_id}_phone",
                "priority": 30,
            },
        ],
        "fusion": {"rule": "highest_priority_above_floor", "confidence_floor": 0.4},
    }
    defaults.update(overrides)
    return PresenceConfig(**defaults)


def test_build_providers_returns_sorted_list():
    """Providers are sorted by priority descending."""
    config = _make_config()
    cache = _StubHaStateCache()
    repo = _StubLocationRepository()

    providers = build_providers(config, cache=cache, location_repository=repo)

    assert len(providers) == 3
    priorities = [p.priority for p in providers]
    assert priorities == sorted(priorities, reverse=True)
    # Highest priority first (ha_bed_sensor at 70)
    assert providers[0].name == "ha_bed_sensor"


def test_build_providers_registers_ha_entities():
    """HaBedSensorProvider.register() is called during build."""
    config = _make_config()
    cache = _StubHaStateCache()
    repo = _StubLocationRepository()

    build_providers(config, cache=cache, location_repository=repo)

    assert "binary_sensor.bed" in cache._registered


def test_collect_required_entities():
    """Only ha_bed_sensor entities are collected (device_tracker deferred)."""
    config = _make_config()
    entities = collect_required_entities(config)
    assert "binary_sensor.bed" in entities


def test_build_providers_with_unknown_provider():
    """Unknown provider name raises ValueError."""
    import pytest

    from backend.services.presence import factory

    original = dict(factory._PROVIDER_BUILDERS)
    try:
        # Remove ha_bed_sensor to test the unknown-provider path.
        factory._PROVIDER_BUILDERS.pop("ha_bed_sensor")
        config = PresenceConfig(
            providers=[{"name": "ha_bed_sensor", "entity_id": "x", "person_id": "y", "room_id": "z"}],
        )
        with pytest.raises(ValueError, match="ha_bed_sensor"):
            build_providers(
                config,
                cache=_StubHaStateCache(),
                location_repository=_StubLocationRepository(),
            )
    finally:
        factory._PROVIDER_BUILDERS.clear()
        factory._PROVIDER_BUILDERS.update(original)


def test_build_all_provider_types():
    """Every provider type can be instantiated from a representative config."""
    config = PresenceConfig(
        providers=[
            {"name": "cts_location", "ttl_seconds": 120, "priority": 50},
            {
                "name": "ha_bed_sensor",
                "entity_id": "binary_sensor.bed",
                "person_id": "mom",
                "room_id": "bedroom",
                "room_name": "Master Bedroom",
                "priority": 70,
            },
            {
                "name": "ha_device_tracker",
                "entity_id_template": "device_tracker.{person_id}_phone",
                "priority": 30,
            },
            {
                "name": "night_anchor",
                "light_entities": ["light.bedroom"],
                "bed_sensor_entity": "binary_sensor.bed_occupancy",
                "anchor_room_id": "bedroom",
                "anchor_room_name": "Master Bedroom",
                "require_last_room_in": ["bedroom"],
                "release_predicates": ["motion outside bedroom in last 5m"],
                "priority": 90,
            },
            {"name": "stale_fallback", "ttl_seconds": 3600, "priority": 10},
            {"name": "unknown_sentinel"},
        ],
        fusion={"rule": "highest_priority_above_floor", "confidence_floor": 0.4},
    )
    cache = _StubHaStateCache()
    repo = _StubLocationRepository()

    providers = build_providers(config, cache=cache, location_repository=repo)

    assert len(providers) == 6
    names = [p.name for p in providers]
    assert "night_anchor" in names
    assert "ha_bed_sensor" in names
    assert "cts_location" in names
    assert "ha_device_tracker" in names
    assert "stale_fallback" in names
    assert "unknown_sentinel" in names
    assert names[0] == "night_anchor"  # highest priority
