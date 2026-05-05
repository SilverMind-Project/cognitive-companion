"""Tests for UnknownProvider."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services.presence import PresenceSource, PresenceStatus
from backend.services.presence.providers.unknown import UnknownProvider


@pytest.mark.asyncio
async def test_always_returns_unknown():
    """UnknownProvider always returns a snapshot with UNKNOWN status."""
    provider = UnknownProvider()
    at = datetime.now(UTC)
    result = await provider.probe("mom", at)

    assert result is not None
    assert result.status == PresenceStatus.UNKNOWN
    assert result.room_id is None
    assert result.room_name is None
    assert result.confidence == 0.0
    assert result.last_seen_at is None
    assert result.dwell_minutes is None
    assert result.sources == (PresenceSource(name="unknown_sentinel", confidence=0.0),)
    assert result.inferred_at == at
    assert result.notes == "no provider matched"


@pytest.mark.asyncio
async def test_priority_is_zero():
    """UnknownProvider has priority 0 (lowest)."""
    provider = UnknownProvider()
    assert provider.priority == 0


@pytest.mark.asyncio
async def test_default_name():
    """UnknownProvider defaults to 'unknown_sentinel'."""
    provider = UnknownProvider()
    assert provider.name == "unknown_sentinel"
