"""Tests for StaleFallbackProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.presence import PresenceStatus
from backend.services.presence.providers.stale_fallback import (
    StaleFallbackProvider,
)

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
    service: PersonLocationService, *, ttl_seconds: int = 3600
) -> StaleFallbackProvider:
    return StaleFallbackProvider(location_service=service, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_state_returns_none():
    """No observation ever -> None (yield to UnknownProvider)."""
    result = await _make_provider(_make_location_service()).probe("mom", datetime.now(UTC))
    assert result is None


@pytest.mark.asyncio
async def test_fresh_state_returns_none():
    """Fresh observation (within TTL) -> None (yield to higher-priority providers)."""
    service = _make_location_service()
    at = datetime.now(UTC)
    await _seed(service, observed_at=at - timedelta(seconds=60))

    result = await _make_provider(service).probe("mom", at)
    assert result is None


@pytest.mark.asyncio
async def test_stale_state_returns_snapshot():
    """Stale observation (past TTL) -> STALE snapshot."""
    service = _make_location_service()
    at = datetime.now(UTC)
    stale_time = at - timedelta(hours=2)
    await _seed(service, observed_at=stale_time)

    result = await _make_provider(service).probe("mom", at)

    assert result is not None
    assert result.status == PresenceStatus.STALE
    assert result.room_name == "bedroom"
    assert result.last_seen_at == stale_time
    assert result.confidence == 0.85
    assert "last_seen" in (result.notes or "").lower()
