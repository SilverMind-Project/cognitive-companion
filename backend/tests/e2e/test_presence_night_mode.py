"""End-to-end night-mode integration test for PresenceService (Block 9).

This test wires the full provider chain (HaStateCache + night_anchor +
ha_bed_sensor + cts_location + stale_fallback + unknown_sentinel) and
simulates the canonical night-mode flow from the design document:

1. **Asleep scenario** (22:00): bedroom lights off + bed sensor on
   → ``PresenceStatus.ASLEEP`` in bedroom.
2. **Release scenario** (bathroom motion): lights still off but CTS
   detects person in bathroom → anchor releases, status transitions
   to ``PresenceStatus.PRESENT_ROOM bathroom``.

No real Redis, HA, or WebSocket is required.  A fake ``HaStateCache``
drives all HA entity state, and an in-memory ``LocationRepository``
provides the CTS location data.

Verification: ``make check`` (runs all tests including this module).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.integrations.ha_state_cache import HaState
from backend.services.cts.location_repository import (
    InMemoryLocationRepository,
)
from backend.services.presence import (
    PresenceService,
    PresenceStatus,
)
from backend.services.presence.config import load_presence_config
from backend.services.presence.factory import build_providers

# ---------------------------------------------------------------------------
# Fake HaStateCache (no WS, no REST)
# ---------------------------------------------------------------------------


@dataclass
class _FakeState:
    entity_id: str
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)
    last_changed: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeHaStateCache:
    """In-process fake of ``HaStateCache`` with direct state mutation."""

    def __init__(self) -> None:
        self._states: dict[str, _FakeState] = {}
        self._history: dict[str, deque[_FakeState]] = {}
        self._registered: set[str] = set()

    # -- Public API (mirrors HaStateCache) --------------------------------

    def get(self, entity_id: str) -> HaState | None:
        fs = self._states.get(entity_id)
        if fs is None:
            return None
        return HaState(
            entity_id=fs.entity_id,
            state=fs.state,
            attributes=fs.attributes,
            last_changed=fs.last_changed,
        )

    def history(self, entity_id: str, *, max_items: int = 32) -> tuple[HaState, ...]:
        dq = self._history.get(entity_id)
        if dq is None:
            return ()
        return tuple(reversed(dq))[:max_items]

    def register(self, entity_id: str) -> None:
        self._registered.add(entity_id)

    async def start(self) -> None:
        pass  # no-op

    async def stop(self) -> None:
        self._states.clear()
        self._history.clear()

    # -- Test helpers (not part of real API) ------------------------------

    def set_state(
        self,
        entity_id: str,
        state: str,
        *,
        attributes: dict[str, Any] | None = None,
        last_changed: datetime | None = None,
    ) -> None:
        """Directly set the cached state for *entity_id*.

        This is the test-only surface that simulates an incoming WS event.
        """
        fs = _FakeState(
            entity_id=entity_id,
            state=state,
            attributes=attributes or {},
            last_changed=last_changed or datetime.now(UTC),
        )
        self._states[entity_id] = fs

        dq = self._history.get(entity_id)
        if dq is None:
            dq = deque(maxlen=32)
            self._history[entity_id] = dq
        dq.append(fs)

    def clear(self) -> None:
        self._states.clear()
        self._history.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_chain(
    cache: FakeHaStateCache,
    location_repo: InMemoryLocationRepository,
    *,
    at: datetime | None = None,
) -> PresenceService:
    """Build the full provider chain from the test fixture config.

    Parameters
    ----------
    cache:
        The fake HA state cache.
    location_repo:
        The in-memory location repository.
    at:
        Deterministic point-in-time for provider probes.

    Returns
    -------
    PresenceService
        A fully wired service ready for ``get()`` calls.
    """
    config = load_presence_config(
        "backend/tests/fixtures/presence_test.yaml"
    )
    providers = build_providers(
        config,
        cache=cache,  # type: ignore[arg-type]  # fake is structurally compatible
        location_repository=location_repo,
    )
    return PresenceService(
        providers=providers,
        fusion_config=config.fusion,
    )


def _seed_bedroom_state(
    repo: InMemoryLocationRepository,
    *,
    person_id: str = "mom",
    room_name: str = "bedroom",
    minutes_ago: int = 60,
    at: datetime | None = None,
) -> None:
    """Insert a ``PersonLocationState`` row via the in-memory repo."""
    now = at or datetime.now(UTC)
    repo.upsert_state(
        person_id=person_id,
        room_name=room_name,
        room_id=1,
        sensor_id="recamera_bedroom",
        confidence=0.85,
        event_time=now - timedelta(minutes=minutes_ago),
    )


def _now_at(hour: int, minute: int = 0) -> datetime:
    """Return a deterministic datetime on today at *hour:minute*."""
    return datetime.now(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Test 1: Asleep scenario (night-mode anchors to ASLEEP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_night_mode_asleep():
    """Scenario 1: lights off + bed sensor on → ASLEEP in bedroom.

    Seed conditions:
    - ``PersonLocationState``: mom in bedroom at 21:55 (65 min ago).
    - ``light.master_bedroom``: off.
    - ``light.hallway``: off.
    - ``binary_sensor.master_bedroom_bed_occupancy``: on.

    Expected: ``PresenceStatus.ASLEEP``, room=bedroom, confidence=0.95,
    sources include ``night_anchor``.
    """
    cache = FakeHaStateCache()
    repo = InMemoryLocationRepository()

    at = _now_at(22, 0)  # 22:00 — probe time

    # Seed location state (mom last seen in bedroom 65 min ago).
    _seed_bedroom_state(repo, minutes_ago=65, at=at)

    # Seed HA cache: lights off, bed sensor on.
    cache.set_state("light.master_bedroom", "off")
    cache.set_state("light.hallway", "off")
    cache.set_state(
        "binary_sensor.master_bedroom_bed_occupancy",
        "on",
        last_changed=at - timedelta(minutes=30),
    )

    service = _build_chain(cache, repo)

    snapshot = await service.get("mom", at=at)

    assert snapshot.status == PresenceStatus.ASLEEP
    assert snapshot.room_name == "bedroom"
    assert snapshot.confidence == 0.95
    assert any(s.name == "night_anchor" for s in snapshot.sources)
    assert snapshot.notes is not None
    assert "anchored" in snapshot.notes


# ---------------------------------------------------------------------------
# Test 2: Release scenario (anchor releases, CTS takes over)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_night_mode_release():
    """Scenario 2: CTS detects bathroom + bed sensor off → CTS wins.

    Realistic flow: person gets out of bed (bed sensor off), CTS detects
    movement to bathroom. Night anchor releases (last room != bedroom),
    bed sensor yields (off), CTS (priority 50) returns PRESENT_ROOM bathroom.

    Seed conditions:
    - ``PersonLocationState``: mom in bathroom (CTS processed event).
    - ``light.master_bedroom``: off (still dark).
    - ``light.hallway``: off.
    - ``binary_sensor.master_bedroom_bed_occupancy``: off (person got up).

    Expected: ``PresenceStatus.PRESENT_ROOM``, room=bathroom.
    """
    cache = FakeHaStateCache()
    repo = InMemoryLocationRepository()

    at = _now_at(22, 5)  # 22:05 — 5 min after asleep scenario

    # Seed location state: mom now in bathroom, 1 min ago (fresh, within 120s TTL).
    _seed_bedroom_state(
        repo, person_id="mom", room_name="bathroom", minutes_ago=1, at=at
    )

    # Seed HA cache: lights still off, bed sensor OFF (person got out of bed).
    cache.set_state("light.master_bedroom", "off")
    cache.set_state("light.hallway", "off")
    cache.set_state("binary_sensor.master_bedroom_bed_occupancy", "off")

    service = _build_chain(cache, repo)

    snapshot = await service.get("mom", at=at)

    # Night anchor yields because last room (bathroom) is not in require list.
    # HaBedSensor yields because bed sensor is off.
    # CTS (priority 50) returns PRESENT_ROOM bathroom.
    assert snapshot.status == PresenceStatus.PRESENT_ROOM
    assert snapshot.room_name == "bathroom"
    assert any(s.name == "cts_location" for s in snapshot.sources)


# ---------------------------------------------------------------------------
# Test 3: Stale CTS + bed sensor → ASLEEP (no CTS evidence, anchor wins)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_night_mode_stale_cts_anchors():
    """When CTS is stale (past TTL) and bed sensor is on, night anchor wins.

    This tests the case where CTS has no fresh evidence but HA bed sensor
    provides strong corroboration.
    """
    cache = FakeHaStateCache()
    repo = InMemoryLocationRepository()

    at = _now_at(22, 0)

    # Seed location state: mom in bedroom 3 hours ago (well past 120s TTL).
    _seed_bedroom_state(repo, minutes_ago=180, at=at)

    # Seed HA cache: lights off, bed sensor on.
    cache.set_state("light.master_bedroom", "off")
    cache.set_state("light.hallway", "off")
    cache.set_state("binary_sensor.master_bedroom_bed_occupancy", "on")

    service = _build_chain(cache, repo)

    snapshot = await service.get("mom", at=at)

    assert snapshot.status == PresenceStatus.ASLEEP
    assert snapshot.room_name == "bedroom"
    assert any(s.name == "night_anchor" for s in snapshot.sources)


# ---------------------------------------------------------------------------
# Test 4: No night conditions → falls through to CTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_night_mode_lights_on_falls_through():
    """When bedroom light is on, night anchor yields → CTS or stale provider answers."""
    cache = FakeHaStateCache()
    repo = InMemoryLocationRepository()

    at = _now_at(14, 0)  # 14:00 — afternoon, lights on

    # Seed location state: mom in bedroom 1 min ago (fresh, within 120s TTL).
    _seed_bedroom_state(repo, minutes_ago=1, at=at)

    # Bedroom light is ON → night anchor yields.
    cache.set_state("light.master_bedroom", "on")
    cache.set_state("light.hallway", "off")
    cache.set_state("binary_sensor.master_bedroom_bed_occupancy", "off")

    service = _build_chain(cache, repo)

    snapshot = await service.get("mom", at=at)

    # Night anchor yields (light on). CTS provider should return PRESENT_ROOM
    # because the last_seen_at is fresh (within 120s TTL).
    assert snapshot.status == PresenceStatus.PRESENT_ROOM
    assert snapshot.room_name == "bedroom"


# ---------------------------------------------------------------------------
# Test 5: Unknown sentinel when no provider matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_night_mode_unknown_sentinel():
    """When no provider returns a candidate, the unknown sentinel answers."""
    cache = FakeHaStateCache()
    repo = InMemoryLocationRepository()

    # No location state at all.
    # HA cache empty.

    service = _build_chain(cache, repo)

    snapshot = await service.get("mom")

    assert snapshot.status == PresenceStatus.UNKNOWN
    assert snapshot.confidence == 0.0
    assert snapshot.sources == ()
