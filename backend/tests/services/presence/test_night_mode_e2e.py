"""Night-mode end-to-end provider test.

Drives the PresenceService + provider chain with a stub HaStateCache
and an in-memory ``PersonLocationService`` (M32: the sole person-location
read API).  Asserts the design doc's section 2.4 flow:

1. At T0 (22:55): location says room=bedroom, last_seen=22:55.
   Cache: bedroom light off, bed sensor on.
   presence.get("mom") @ 23:30 returns status=ASLEEP, room=bedroom.

2. At T1 (02:30): Cache flips bathroom_motion = on.
   A fresh bathroom observation simulates CTS processing the event:
   room=bathroom, last_seen=02:30. This goes through
   ``ingest_observation`` (not a raw repo insert) so the state machine
   correctly closes the bedroom segment before opening the bathroom one --
   two independently-inserted "open" segments would violate the one-open-
   segment-per-person invariant ``where_is()`` relies on.
   presence.get("mom") @ 02:31 returns status=PRESENT_ROOM, room=bathroom
   (anchor released by motion-predicate).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.integrations.ha_state_cache import HaState
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.presence import PresenceService
from backend.services.presence.config import PresenceConfig
from backend.services.presence.factory import build_providers

# ---------------------------------------------------------------------------
# Stub implementations
# ---------------------------------------------------------------------------


class _StubHaStateCache:
    """Minimal stub of HaStateCache backed by a dict."""

    def __init__(self) -> None:
        self._states: dict[str, HaState] = {}
        self._registered: set[str] = set()

    def get(self, entity_id: str) -> HaState | None:
        return self._states.get(entity_id)

    def register(self, entity_id: str) -> None:
        self._registered.add(entity_id)

    def set_state(self, entity_id: str, state: str, last_changed: datetime) -> None:
        self._states[entity_id] = HaState(
            entity_id=entity_id,
            state=state,
            attributes={},
            last_changed=last_changed,
        )


def _make_location_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(room_names={1: "bedroom", 2: "bathroom"}),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


async def _seed_location(
    service: PersonLocationService,
    *,
    person_id: str = "mom",
    room_id: int = 1,
    room_name: str = "bedroom",
    confidence: float = 0.85,
    observed_at: datetime,
) -> None:
    """Ingest a room observation through the real state machine.

    Using ``ingest_observation`` (rather than a raw repo insert) keeps the
    one-open-segment-per-person invariant intact when a test seeds a room
    change after an initial seed.
    """
    await service.ingest_observation(
        person_id=person_id,
        observed_at=observed_at,
        source="world_tracker",
        room_id=room_id,
        confidence=confidence,
        metadata={"room_name": room_name},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_minimal_config() -> PresenceConfig:
    """Create a minimal config that includes night_anchor + location_service."""
    return PresenceConfig(
        providers=[
            {
                "name": "night_anchor",
                "light_entities": ["light.bedroom"],
                "bed_sensor_entity": "binary_sensor.bed_occupancy",
                "anchor_room_id": "bedroom",
                "anchor_room_name": "Master Bedroom",
                "require_last_room_in": ["bedroom", "hallway"],
                "release_predicates": ["motion outside bedroom in last 5m"],
                "confidence": 0.95,
                "priority": 90,
            },
            {
                "name": "location_service",
                "priority": 50,
            },
        ],
        fusion={"rule": "highest_priority_above_floor", "confidence_floor": 0.4},
    )


# ---------------------------------------------------------------------------
# Tests: the design doc's section 2.4 flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_night_mode_anchor_23_30():
    """At 23:30: lights off + bed sensor on + last room=bedroom -> ASLEEP."""
    cache = _StubHaStateCache()
    location_service = _make_location_service()

    # Setup: bedroom light off, bed sensor on.
    t0 = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    cache.set_state("light.bedroom", "off", t0)
    cache.set_state("binary_sensor.bed_occupancy", "on", t0)

    # Setup: last known location is bedroom.
    await _seed_location(location_service, observed_at=t0)

    # Build the service.
    config = _make_minimal_config()
    providers = build_providers(config, cache=cache, location_service=location_service)
    service = PresenceService(providers=providers, fusion_config=config.fusion)

    # Query at 23:30.
    query_time = datetime(2026, 5, 3, 23, 30, 0, tzinfo=UTC)
    result = await service.get("mom", at=query_time)

    assert result.status.value == "asleep"
    assert result.room_id == "bedroom"
    assert result.room_name == "Master Bedroom"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_night_mode_anchor_released_at_02_30():
    """At 02:30: motion outside bedroom detected -> anchor releases."""
    cache = _StubHaStateCache()
    location_service = _make_location_service()

    # Setup: bedroom light off, bed sensor on.
    t0 = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    cache.set_state("light.bedroom", "off", t0)
    cache.set_state("binary_sensor.bed_occupancy", "on", t0)

    # Setup: last known location is bedroom.
    await _seed_location(location_service, observed_at=t0)

    # Build the service.
    config = _make_minimal_config()
    providers = build_providers(config, cache=cache, location_service=location_service)
    service = PresenceService(providers=providers, fusion_config=config.fusion)

    # At 02:30, bathroom motion is detected -> anchor releases.
    t1 = datetime(2026, 5, 4, 2, 30, 0, tzinfo=UTC)
    cache.set_state("binary_sensor.hallway_motion", "on", t1)

    # Also seed a fresh bathroom observation to simulate CTS processing the event.
    await _seed_location(location_service, room_id=2, room_name="bathroom", observed_at=t1)

    # Query at 02:31.
    query_time = datetime(2026, 5, 4, 2, 31, 0, tzinfo=UTC)
    result = await service.get("mom", at=query_time)

    # Anchor released -> falls through to location_service -> PRESENT_ROOM bathroom.
    assert result.status.value == "present_room"
    assert result.room_name == "bathroom"


@pytest.mark.asyncio
async def test_night_mode_anchor_no_motion_stays_asleep():
    """No motion outside bedroom -> anchor stays active."""
    cache = _StubHaStateCache()
    location_service = _make_location_service()

    # Setup: bedroom light off, bed sensor on.
    t0 = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    cache.set_state("light.bedroom", "off", t0)
    cache.set_state("binary_sensor.bed_occupancy", "on", t0)

    # Setup: last known location is bedroom.
    await _seed_location(location_service, observed_at=t0)

    # Build the service.
    config = _make_minimal_config()
    providers = build_providers(config, cache=cache, location_service=location_service)
    service = PresenceService(providers=providers, fusion_config=config.fusion)

    # Query at 02:30 (no motion detected).
    query_time = datetime(2026, 5, 4, 2, 30, 0, tzinfo=UTC)
    result = await service.get("mom", at=query_time)

    assert result.status.value == "asleep"
    assert result.room_id == "bedroom"
