"""Tests for NightAnchorProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.integrations.ha_state_cache import HaState
from backend.models.person import PersonLocationHistory, PersonLocationState
from backend.services.presence import PresenceStatus
from backend.services.presence.anchor_rules import compile_predicate
from backend.services.presence.providers.night_anchor import (
    NightAnchorProvider,
)

# ---------------------------------------------------------------------------
# Stub implementations
# ---------------------------------------------------------------------------


class _StubCache:
    """Minimal stub of HaStateCache backed by a dict."""

    def __init__(self, states: dict[str, HaState] | None = None) -> None:
        self._states: dict[str, HaState] = states or {}
        self._registered: set[str] = set()

    def get(self, entity_id: str) -> HaState | None:
        return self._states.get(entity_id)

    def register(self, entity_id: str) -> None:
        self._registered.add(entity_id)


class _StubRepository:
    """Minimal stub implementing the LocationRepository protocol."""

    def __init__(self, state: PersonLocationState | None = None) -> None:
        self._state = state

    def get_state(self, person_id: str) -> PersonLocationState | None:
        return self._state

    def get_open_history_row(self, person_id, room_name=None):
        return None

    def upsert_state(self, **kwargs: Any) -> PersonLocationState:  # type: ignore[override]
        raise NotImplementedError

    def close_open_history(self, **kwargs: Any) -> int:  # type: ignore[override]
        raise NotImplementedError

    def append_history(self, **kwargs: Any) -> PersonLocationHistory:  # type: ignore[override]
        raise NotImplementedError

    def current_room_for(self, person_id: str) -> str | None:  # type: ignore[override]
        if self._state is None:
            return None
        return self._state.current_room_name

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_state(
    *,
    person_id: str = "mom",
    room_name: str = "bedroom",
    room_id: int = 1,
    last_seen_at: datetime | None = None,
    confidence: float = 0.85,
) -> PersonLocationState:
    if last_seen_at is None:
        last_seen_at = datetime.now(UTC)
    return PersonLocationState(
        person_id=person_id,
        current_room_id=room_id,
        current_room_name=room_name,
        last_seen_at=last_seen_at,
        confidence=confidence,
    )


@pytest.fixture
def now():
    return datetime.now(UTC)


def _make_provider(
    cache: _StubCache,
    repo: _StubRepository,
    release_predicates: list | None = None,
    confidence: float | None = None,
) -> NightAnchorProvider:
    return NightAnchorProvider(
        cache=cache,
        location_repository_factory=lambda: repo,
        light_entities=["light.bedroom"],
        bed_sensor_entity="binary_sensor.master_bedroom_bed_occupancy",
        anchor_room_id="bedroom",
        anchor_room_name="Master Bedroom",
        require_last_room_in=["bedroom", "hallway"],
        release_predicates=release_predicates or [],
        confidence=confidence if confidence is not None else 0.95,
    )


# ---------------------------------------------------------------------------
# Tests (8 cases from the design doc)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lights_on_returns_none(now):
    """Lights on -> None."""
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom",
                state="on",
                attributes={},
                last_changed=now,
            ),
        }
    )
    provider = _make_provider(_StubCache(), cache)
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_bed_sensor_off_returns_none(now):
    """Lights off, bed sensor off -> None (no fallback in v0)."""
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom",
                state="off",
                attributes={},
                last_changed=now - timedelta(minutes=30),
            ),
            "binary_sensor.master_bedroom_bed_occupancy": HaState(
                entity_id="binary_sensor.master_bedroom_bed_occupancy",
                state="off",
                attributes={},
                last_changed=now,
            ),
        }
    )
    provider = _make_provider(_StubCache(), cache)
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_wrong_room_returns_none(now):
    """Lights off, bed sensor on, last room kitchen -> None."""
    repo = _StubRepository(_make_state(room_name="kitchen"))
    provider = _make_provider(_StubCache(), repo)
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_anchor_activates(now):
    """Lights off, bed sensor on, last room bedroom -> ASLEEP."""
    last_seen = now - timedelta(minutes=35)
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom",
                state="off",
                attributes={},
                last_changed=now - timedelta(minutes=35),
            ),
            "binary_sensor.master_bedroom_bed_occupancy": HaState(
                entity_id="binary_sensor.master_bedroom_bed_occupancy",
                state="on",
                attributes={},
                last_changed=now,
            ),
        }
    )
    repo = _StubRepository(_make_state(last_seen_at=last_seen))
    provider = _make_provider(cache, repo)
    result = await provider.probe("mom", now)

    assert result is not None
    assert result.status == PresenceStatus.ASLEEP
    assert result.room_id == "bedroom"
    assert result.room_name == "Master Bedroom"
    assert result.confidence == 0.95
    assert result.last_seen_at == last_seen
    assert "anchored" in (result.notes or "").lower()


@pytest.mark.asyncio
async def test_release_predicate_motion(now):
    """Release predicate motion outside bedroom -> None."""
    repo = _StubRepository(_make_state())
    release_predicates = [
        compile_predicate("motion outside bedroom in last 5m"),
    ]
    provider = _make_provider(
        _StubCache(),
        repo,
        release_predicates=release_predicates,
    )
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_no_state_returns_none(now):
    """Lights off, bed sensor on, no PersonLocationState -> None."""
    provider = _make_provider(_StubCache(), _StubRepository(None))
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_no_release_predicates_anchors(now):
    """release_predicates=[] -> anchor activates (never releases on its own)."""
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom",
                state="off",
                attributes={},
                last_changed=now - timedelta(minutes=30),
            ),
            "binary_sensor.master_bedroom_bed_occupancy": HaState(
                entity_id="binary_sensor.master_bedroom_bed_occupancy",
                state="on",
                attributes={},
                last_changed=now,
            ),
        }
    )
    repo = _StubRepository(_make_state())
    provider = _make_provider(
        cache,
        repo,
        release_predicates=[],
    )
    result = await provider.probe("mom", now)
    assert result is not None
    assert result.status == PresenceStatus.ASLEEP


@pytest.mark.asyncio
async def test_confidence_propagated(now):
    """Confidence is propagated from constructor."""
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom",
                state="off",
                attributes={},
                last_changed=now - timedelta(minutes=30),
            ),
            "binary_sensor.master_bedroom_bed_occupancy": HaState(
                entity_id="binary_sensor.master_bedroom_bed_occupancy",
                state="on",
                attributes={},
                last_changed=now,
            ),
        }
    )
    repo = _StubRepository(_make_state())
    provider = _make_provider(
        cache,
        repo,
        confidence=0.88,
    )
    result = await provider.probe("mom", now)
    assert result is not None
    assert result.confidence == 0.88
