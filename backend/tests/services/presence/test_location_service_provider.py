"""Tests for LocationServiceProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import SourceTag
from backend.services.presence import (
    PresenceSource,
    PresenceStatus,
)
from backend.services.presence.providers.location_service import LocationServiceProvider

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
    source: SourceTag = "world_tracker",
    observed_at: datetime,
) -> None:
    await service.ingest_observation(
        person_id=person_id,
        observed_at=observed_at,
        source=source,
        room_id=room_id,
        confidence=confidence,
        metadata={"room_name": room_name},
    )


def _make_provider(
    service: PersonLocationService,
    *,
    ttl_seconds_by_source: dict[SourceTag, int] | None = None,
) -> LocationServiceProvider:
    return LocationServiceProvider(
        location_service=service,
        ttl_seconds_by_source=ttl_seconds_by_source,
    )


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
    assert result.sources == (PresenceSource(name="location_service", confidence=0.85),)
    assert result.dwell_minutes is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "ttl", "elapsed_fresh", "elapsed_stale"),
    [
        ("world_tracker", 120, 100, 150),
        ("face_sighting", 2700, 2600, 2800),
        ("sensor", 1800, 1700, 1900),
        ("manual", 86400, 80000, 90000),
    ],
)
async def test_per_source_ttl_matrix(
    source: SourceTag, ttl: int, elapsed_fresh: int, elapsed_stale: int
):
    service = _make_location_service()
    at = datetime.now(UTC)

    # Fresh observation within TTL
    await _seed(service, source=source, observed_at=at - timedelta(seconds=elapsed_fresh))
    provider = _make_provider(service)
    fresh_res = await provider.probe("mom", at)
    assert fresh_res is not None
    assert fresh_res.status == PresenceStatus.PRESENT_ROOM

    # Stale observation beyond TTL
    service_stale = _make_location_service()
    await _seed(service_stale, source=source, observed_at=at - timedelta(seconds=elapsed_stale))
    provider_stale = _make_provider(service_stale)
    stale_res = await provider_stale.probe("mom", at)
    assert stale_res is not None
    assert stale_res.status == PresenceStatus.STALE


@pytest.mark.asyncio
async def test_unknown_source_fallback():
    service = _make_location_service()
    at = datetime.now(UTC)
    # Seed with custom unknown source
    await service.ingest_observation(
        person_id="mom",
        observed_at=at - timedelta(seconds=130),
        source="unknown_custom",  # type: ignore[arg-type]
        room_id=1,
        confidence=0.85,
        metadata={"room_name": "bedroom"},
    )

    provider = _make_provider(service)  # min TTL in default map is 120 (world_tracker)
    result = await provider.probe("mom", at)

    assert result is not None
    # 130s elapsed > min TTL (120s), so STALE
    assert result.status == PresenceStatus.STALE


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
