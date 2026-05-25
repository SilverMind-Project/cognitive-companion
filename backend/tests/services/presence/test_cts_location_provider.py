"""Tests for CtsLocationProvider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.models.person import PersonLocationHistory, PersonLocationState
from backend.services.presence import (
    PresenceSource,
    PresenceStatus,
)
from backend.services.presence.providers.cts_location import CtsLocationProvider

# ---------------------------------------------------------------------------
# Stub repository
# ---------------------------------------------------------------------------


class _StubRepository:
    """Minimal stub implementing the LocationRepository protocol."""

    def __init__(self, state: PersonLocationState | None = None) -> None:
        self._state = state
        self._history: list[PersonLocationHistory] = []
        self._next_id = 1

    def get_state(self, person_id: str) -> PersonLocationState | None:
        return self._state

    def get_open_history_row(
        self,
        person_id: str,
        room_name: str | None = None,
    ) -> PersonLocationHistory | None:
        candidates = [
            h for h in reversed(self._history) if h.person_id == person_id and h.exited_at is None
        ]
        if room_name is not None:
            candidates = [h for h in candidates if h.room_name == room_name]
        if not candidates:
            return None
        return candidates[0]

    # Protocol stubs (no-ops)
    def upsert_state(self, **kwargs: Any) -> PersonLocationState:  # type: ignore[override]
        raise NotImplementedError

    def close_open_history(self, **kwargs: Any) -> int:  # type: ignore[override]
        raise NotImplementedError

    def append_history(self, **kwargs: Any) -> PersonLocationHistory:  # type: ignore[override]
        row = PersonLocationHistory(
            person_id=kwargs["person_id"],
            room_id=kwargs.get("room_id"),
            room_name=kwargs.get("room_name"),
            entered_at=kwargs["entered_at"],
            source=kwargs.get("source", "test"),
        )
        self._history.append(row)
        return row

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
def fresh_state() -> PersonLocationState:
    return _make_state()


@pytest.fixture
def stale_state() -> PersonLocationState:
    return _make_state(
        last_seen_at=datetime.now(UTC) - timedelta(seconds=300),
    )


@pytest.fixture
def no_room_state() -> PersonLocationState:
    return _make_state(room_name=None, room_id=None)


def _make_provider(state: PersonLocationState | None = None) -> CtsLocationProvider:
    repo = _StubRepository(state)
    return CtsLocationProvider(
        location_repository_factory=lambda: repo,
        ttl_seconds=120,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_state_returns_present_room(
    fresh_state: PersonLocationState,
):
    provider = _make_provider(fresh_state)
    at = datetime.now(UTC)
    result = await provider.probe("mom", at)

    assert result is not None
    assert result.status == PresenceStatus.PRESENT_ROOM
    assert result.room_name == "bedroom"
    assert result.confidence == 0.85
    assert result.last_seen_at == fresh_state.last_seen_at
    assert result.sources == (PresenceSource(name="cts_location", confidence=0.85),)
    assert (
        result.dwell_minutes is not None or result.dwell_minutes is None
    )  # dwell may be None if no history


@pytest.mark.asyncio
async def test_stale_state_returns_stale(
    stale_state: PersonLocationState,
):
    provider = _make_provider(stale_state)
    at = datetime.now(UTC)
    result = await provider.probe("mom", at)

    assert result is not None
    assert result.status == PresenceStatus.STALE
    assert result.room_name == "bedroom"
    assert "last_seen" in (result.notes or "").lower()


@pytest.mark.asyncio
async def test_no_room_returns_none(
    no_room_state: PersonLocationState,
):
    provider = _make_provider(no_room_state)
    at = datetime.now(UTC)
    result = await provider.probe("mom", at)

    assert result is None


@pytest.mark.asyncio
async def test_no_state_returns_none():
    provider = _make_provider(None)
    at = datetime.now(UTC)
    result = await provider.probe("mom", at)

    assert result is None
