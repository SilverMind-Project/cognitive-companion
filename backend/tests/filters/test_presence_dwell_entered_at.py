"""WTR7: PresenceDwellFilter uses entered_at and injected now."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.filters.builtin.presence_dwell import PresenceDwellFilter


@pytest.mark.asyncio
async def test_dwell_uses_entered_at_and_injected_now():
    """Dwell must be computed from segment entered_at, using the injected now."""
    flt = PresenceDwellFilter()
    mock_svc = MagicMock()
    mock_svc.current_dwell = AsyncMock()
    services = MagicMock()
    services.person_location = mock_svc

    # Segment entered 10 minutes ago.
    entered = datetime.now(UTC) - timedelta(minutes=10)
    mock_dwell = MagicMock()
    mock_dwell.entered_at = entered
    mock_svc.current_dwell.return_value = mock_dwell

    # Injected now = entered + 10 minutes → dwell = 10 min, min_minutes=5 → passes.
    now = entered + timedelta(minutes=10)
    result = await flt.evaluate(
        {"person_id": "alice", "min_minutes": 5},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is True


@pytest.mark.asyncio
async def test_dwell_below_threshold_fails():
    """When dwell is below min_minutes, filter must return False."""
    flt = PresenceDwellFilter()
    mock_svc = MagicMock()
    mock_svc.current_dwell = AsyncMock()
    services = MagicMock()
    services.person_location = mock_svc

    entered = datetime.now(UTC) - timedelta(minutes=2)
    mock_dwell = MagicMock()
    mock_dwell.entered_at = entered
    mock_svc.current_dwell.return_value = mock_dwell

    now = entered + timedelta(minutes=2)
    result = await flt.evaluate(
        {"person_id": "alice", "min_minutes": 5},
        sensor=None,
        now=now,
        services=services,
    )
    assert result is False
