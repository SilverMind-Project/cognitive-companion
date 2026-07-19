"""Tests for CtsLocationProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.presence import (
    PresenceSource,
    PresenceStatus,
)
from backend.services.presence.providers.cts_location import CtsLocationProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_location_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(room_names={1: "bedroom"}),
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


def _make_provider(
    service: PersonLocationService, *, ttl_seconds: int = 120
) -> CtsLocationProvider:
    return CtsLocationProvider(location_service=service, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_state_returns_present_room():
    service = _make_location_service()
    at = datetime.now(UTC)
    await _seed(service, observed_at=at)

    provider = _make_provider(service)
    result = await provider.probe("mom", at)

    assert result is not None
    assert result.status == PresenceStatus.PRESENT_ROOM
    assert result.room_name == "bedroom"
    assert result.confidence == 0.85
    assert result.last_seen_at == at
    assert result.sources == (PresenceSource(name="cts_location", confidence=0.85),)
    assert result.dwell_minutes is not None


@pytest.mark.asyncio
async def test_stale_state_returns_stale():
    service = _make_location_service()
    at = datetime.now(UTC)
    stale_time = at - timedelta(seconds=300)
    await _seed(service, observed_at=stale_time)

    provider = _make_provider(service)
    result = await provider.probe("mom", at)

    assert result is not None
    assert result.status == PresenceStatus.STALE
    assert result.room_name == "bedroom"
    assert "last_seen" in (result.notes or "").lower()


@pytest.mark.asyncio
async def test_no_room_returns_none():
    """A room-less observation opens no segment -> yield to next provider."""
    service = _make_location_service()
    at = datetime.now(UTC)
    await service.ingest_observation(
        person_id="mom",
        observed_at=at,
        source="world_tracker",
        room_id=None,
        confidence=0.85,
    )

    provider = _make_provider(service)
    result = await provider.probe("mom", at)

    assert result is None


@pytest.mark.asyncio
async def test_no_state_returns_none():
    service = _make_location_service()
    provider = _make_provider(service)
    result = await provider.probe("mom", datetime.now(UTC))

    assert result is None
