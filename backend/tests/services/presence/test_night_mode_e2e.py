"""Night-mode end-to-end provider test.

Drives the PresenceService + provider chain with a stub HaStateCache
and stub LocationRepository.  Asserts the design doc's section 2.4
flow:

1. At T0 (22:55): PersonLocationState says room=bedroom, last_seen=22:55.
   Cache: bedroom light off, bed sensor on.
   presence.get("mom") @ 23:30 returns status=ASLEEP, room=bedroom.

2. At T1 (02:30): Cache flips bathroom_motion = on.
   PersonLocationState is mutated to simulate CTS processing the event:
   room=bathroom, last_seen=02:30.
   presence.get("mom") @ 02:31 returns status=PRESENT_ROOM, room=bathroom
   (anchor released by motion-predicate).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from backend.integrations.ha_state_cache import HaState
from backend.models.person import PersonLocationHistory, PersonLocationState
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


class _StubLocationRepository:
    """Minimal stub implementing the LocationRepository protocol."""

    def __init__(self) -> None:
        self._states: dict[str, PersonLocationState] = {}

    def get_state(self, person_id: str) -> PersonLocationState | None:
        return self._states.get(person_id)

    def set_state(self, state: PersonLocationState) -> None:
        self._states[state.person_id] = state

    def get_open_history_row(self, person_id, room_name=None):
        return None

    def upsert_state(self, **kwargs: Any) -> PersonLocationState:  # type: ignore[override]
        raise NotImplementedError

    def close_open_history(self, **kwargs: Any) -> int:  # type: ignore[override]
        raise NotImplementedError

    def append_history(self, **kwargs: Any) -> PersonLocationHistory:  # type: ignore[override]
        raise NotImplementedError

    def current_room_for(self, person_id: str) -> str | None:  # type: ignore[override]
        state = self._states.get(person_id)
        return state.current_room_name if state is not None else None

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_minimal_config() -> PresenceConfig:
    """Create a minimal config that includes night_anchor + cts_location."""
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
                "name": "cts_location",
                "ttl_seconds": 120,
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
    repo = _StubLocationRepository()

    # Setup: bedroom light off, bed sensor on.
    t0 = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    cache.set_state("light.bedroom", "off", t0)
    cache.set_state("binary_sensor.bed_occupancy", "on", t0)

    # Setup: last known location is bedroom.
    last_seen = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    repo.set_state(
        PersonLocationState(
            person_id="mom",
            current_room_id=1,
            current_room_name="bedroom",
            last_seen_at=last_seen,
            confidence=0.85,
        ),
    )

    # Build the service.
    config = _make_minimal_config()
    providers = build_providers(config, cache=cache, location_repository_factory=lambda: repo)
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
    repo = _StubLocationRepository()

    # Setup: bedroom light off, bed sensor on.
    t0 = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    cache.set_state("light.bedroom", "off", t0)
    cache.set_state("binary_sensor.bed_occupancy", "on", t0)

    # Setup: last known location is bedroom.
    last_seen = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    repo.set_state(
        PersonLocationState(
            person_id="mom",
            current_room_id=1,
            current_room_name="bedroom",
            last_seen_at=last_seen,
            confidence=0.85,
        ),
    )

    # Build the service.
    config = _make_minimal_config()
    providers = build_providers(config, cache=cache, location_repository_factory=lambda: repo)
    service = PresenceService(providers=providers, fusion_config=config.fusion)

    # At 02:30, bathroom motion is detected -> anchor releases.
    t1 = datetime(2026, 5, 4, 2, 30, 0, tzinfo=UTC)
    cache.set_state("binary_sensor.hallway_motion", "on", t1)

    # Also mutate the repo to simulate CTS processing the bathroom event.
    repo.set_state(
        PersonLocationState(
            person_id="mom",
            current_room_id=2,
            current_room_name="bathroom",
            last_seen_at=t1,
            confidence=0.85,
        ),
    )

    # Query at 02:31.
    query_time = datetime(2026, 5, 4, 2, 31, 0, tzinfo=UTC)
    result = await service.get("mom", at=query_time)

    # Anchor released -> falls through to cts_location -> PRESENT_ROOM bathroom.
    assert result.status.value == "present_room"
    assert result.room_name == "bathroom"


@pytest.mark.asyncio
async def test_night_mode_anchor_no_motion_stays_asleep():
    """No motion outside bedroom -> anchor stays active."""
    cache = _StubHaStateCache()
    repo = _StubLocationRepository()

    # Setup: bedroom light off, bed sensor on.
    t0 = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    cache.set_state("light.bedroom", "off", t0)
    cache.set_state("binary_sensor.bed_occupancy", "on", t0)

    # Setup: last known location is bedroom.
    last_seen = datetime(2026, 5, 3, 22, 55, 0, tzinfo=UTC)
    repo.set_state(
        PersonLocationState(
            person_id="mom",
            current_room_id=1,
            current_room_name="bedroom",
            last_seen_at=last_seen,
            confidence=0.85,
        ),
    )

    # Build the service.
    config = _make_minimal_config()
    providers = build_providers(config, cache=cache, location_repository_factory=lambda: repo)
    service = PresenceService(providers=providers, fusion_config=config.fusion)

    # Query at 02:30 (no motion detected).
    query_time = datetime(2026, 5, 4, 2, 30, 0, tzinfo=UTC)
    result = await service.get("mom", at=query_time)

    assert result.status.value == "asleep"
    assert result.room_id == "bedroom"
