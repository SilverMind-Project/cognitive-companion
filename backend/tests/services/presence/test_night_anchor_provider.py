"""Tests for NightAnchorProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.integrations.ha_state_cache import HaState
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
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


def _make_location_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(room_names={1: "bedroom", 2: "kitchen"}),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


async def _seed(
    service: PersonLocationService,
    *,
    person_id: str = "mom",
    room_id: int = 1,
    room_name: str = "bedroom",
    confidence: float = 0.85,
    observed_at: datetime,
) -> None:
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


@pytest.fixture
def now():
    return datetime.now(UTC)


def _make_provider(
    cache: _StubCache,
    location_service: PersonLocationService,
    release_predicates: list | None = None,
    confidence: float | None = None,
) -> NightAnchorProvider:
    return NightAnchorProvider(
        cache=cache,
        location_service=location_service,
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
    provider = _make_provider(cache, _make_location_service())
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
    provider = _make_provider(cache, _make_location_service())
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_wrong_room_returns_none(now):
    """Lights off, bed sensor on, last room kitchen -> None."""
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom", state="off", attributes={}, last_changed=now
            ),
            "binary_sensor.master_bedroom_bed_occupancy": HaState(
                entity_id="binary_sensor.master_bedroom_bed_occupancy",
                state="on",
                attributes={},
                last_changed=now,
            ),
        }
    )
    service = _make_location_service()
    await _seed(service, room_id=2, room_name="kitchen", observed_at=now)
    provider = _make_provider(cache, service)
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
    service = _make_location_service()
    await _seed(service, observed_at=last_seen)
    provider = _make_provider(cache, service)
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
    service = _make_location_service()
    await _seed(service, observed_at=now)
    release_predicates = [
        compile_predicate("motion outside bedroom in last 5m"),
    ]
    provider = _make_provider(
        _StubCache(),
        service,
        release_predicates=release_predicates,
    )
    result = await provider.probe("mom", now)
    assert result is None


@pytest.mark.asyncio
async def test_no_state_returns_none(now):
    """Lights off, bed sensor on, no observation ever -> None."""
    cache = _StubCache(
        {
            "light.bedroom": HaState(
                entity_id="light.bedroom", state="off", attributes={}, last_changed=now
            ),
            "binary_sensor.master_bedroom_bed_occupancy": HaState(
                entity_id="binary_sensor.master_bedroom_bed_occupancy",
                state="on",
                attributes={},
                last_changed=now,
            ),
        }
    )
    provider = _make_provider(cache, _make_location_service())
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
    service = _make_location_service()
    await _seed(service, observed_at=now)
    provider = _make_provider(
        cache,
        service,
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
    service = _make_location_service()
    await _seed(service, observed_at=now)
    provider = _make_provider(
        cache,
        service,
        confidence=0.88,
    )
    result = await provider.probe("mom", now)
    assert result is not None
    assert result.confidence == 0.88
