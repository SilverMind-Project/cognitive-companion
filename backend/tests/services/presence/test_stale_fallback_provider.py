"""Tests for StaleFallbackProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.models.person import PersonLocationHistory, PersonLocationState
from backend.services.presence import PresenceStatus
from backend.services.presence.providers.stale_fallback import (
    StaleFallbackProvider,
)

# ---------------------------------------------------------------------------
# Stub repository
# ---------------------------------------------------------------------------


class _StubRepository:
    """Minimal stub implementing the LocationRepository protocol."""

    def __init__(self, state: PersonLocationState | None = None) -> None:
        self._state = state

    def get_state(self, person_id: str) -> PersonLocationState | None:
        return self._state

    def get_open_history_row(
        self,
        person_id: str,
        room_name: str | None = None,
    ) -> PersonLocationHistory | None:
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
def provider():
    return StaleFallbackProvider(
        location_repository=_StubRepository(),
        ttl_seconds=3600,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_state_returns_none(provider: StaleFallbackProvider):
    """No state row -> None (yield to UnknownProvider)."""
    provider._repo = _StubRepository(None)
    result = await provider.probe("mom", datetime.now(UTC))
    assert result is None


@pytest.mark.asyncio
async def test_fresh_state_returns_none(provider: StaleFallbackProvider):
    """Fresh state (within TTL) -> None (yield to higher-priority providers)."""
    fresh_time = datetime.now(UTC) - timedelta(seconds=60)
    provider._repo = _StubRepository(_make_state(last_seen_at=fresh_time))
    result = await provider.probe("mom", datetime.now(UTC))
    assert result is None


@pytest.mark.asyncio
async def test_stale_state_returns_snapshot(provider: StaleFallbackProvider):
    """Stale state (past TTL) -> STALE snapshot."""
    stale_time = datetime.now(UTC) - timedelta(hours=2)
    provider._repo = _StubRepository(_make_state(last_seen_at=stale_time))
    result = await provider.probe("mom", datetime.now(UTC))

    assert result is not None
    assert result.status == PresenceStatus.STALE
    assert result.room_name == "bedroom"
    assert result.last_seen_at == stale_time
    assert result.confidence == 0.85
    assert "last_seen" in (result.notes or "").lower()


@pytest.mark.asyncio
async def test_no_last_seen_at_returns_none(provider: StaleFallbackProvider):
    """last_seen_at is None -> None (yield to UnknownProvider)."""
    state = _make_state(last_seen_at=None)
    provider._repo = _StubRepository(state)
    result = await provider.probe("mom", datetime.now(UTC))
    assert result is None
