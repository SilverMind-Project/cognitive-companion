"""Tests for PresenceService."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services.presence import (
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)
from backend.services.presence.service import PresenceService

# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal provider that always returns a fixed snapshot or None."""

    def __init__(
        self,
        snapshot: PresenceSnapshot | None,
        name: str = "stub",
        priority: int = 50,
    ) -> None:
        self._snapshot = snapshot
        self._name = name
        self._priority = priority

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    async def probe(
        self,
        person_id: str,
        at: datetime,
    ) -> PresenceSnapshot | None:
        return self._snapshot


def _make_snapshot(
    *,
    person_id: str = "mom",
    status: PresenceStatus = PresenceStatus.PRESENT_ROOM,
    confidence: float = 0.85,
    room_name: str = "bedroom",
) -> PresenceSnapshot:
    at = datetime.now(UTC)
    return PresenceSnapshot(
        person_id=person_id,
        status=status,
        room_id=1,
        room_name=room_name,
        confidence=confidence,
        last_seen_at=at,
        dwell_minutes=10.0,
        sources=(PresenceSource(name="stub", confidence=confidence),),
        inferred_at=at,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_provider_returns_snapshot():
    snapshot = _make_snapshot()
    provider = _StubProvider(snapshot, priority=50)
    service = PresenceService(providers=[provider])

    result = await service.get("mom")

    assert result.status == PresenceStatus.PRESENT_ROOM
    assert result.room_name == "bedroom"
    assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_provider_returns_none_gives_unknown():
    provider = _StubProvider(None, priority=50)
    service = PresenceService(providers=[provider])

    result = await service.get("mom")

    assert result.status == PresenceStatus.UNKNOWN
    assert result.sources == ()
    assert result.notes == "no provider matched"


@pytest.mark.asyncio
async def test_higher_priority_provider_wins_when_lower_returns():
    high = _StubProvider(_make_snapshot(room_name="bedroom"), priority=70)
    low = _StubProvider(_make_snapshot(room_name="kitchen"), priority=30)
    service = PresenceService(providers=[low, high])

    result = await service.get("mom")

    # Higher priority (70) wins
    assert result.room_name == "bedroom"


@pytest.mark.asyncio
async def test_confidence_floor_excludes_low_confidence():
    low_conf = _make_snapshot(confidence=0.3)
    high_conf = _make_snapshot(confidence=0.85)
    low_provider = _StubProvider(low_conf, priority=70)
    high_provider = _StubProvider(high_conf, priority=30)
    service = PresenceService(
        providers=[low_provider, high_provider],
        confidence_floor=0.5,
    )

    result = await service.get("mom")

    # Low confidence (0.3) is below floor (0.5), so falls through to high
    assert result.room_name == "bedroom"
    assert result.confidence == 0.85


@pytest.mark.asyncio
async def test_inferred_at_is_set_to_passed_at():
    provider = _StubProvider(_make_snapshot())
    service = PresenceService(providers=[provider])

    at = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
    result = await service.get("mom", at=at)

    assert result.inferred_at == at
