"""Unit tests for GaitTrendService: envelope mapping and trend classification."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.schemas.gait import GaitTrendEnvelope
from backend.services.gait_trend_service import GaitTrendService


def _make_row(
    local_date: date,
    median_speed_m_s: float = 0.9,
    bout_count: int = 5,
    total_walking_s: float = 120.0,
) -> dict:
    return {
        "identity_id": "alice",
        "local_date": local_date.isoformat(),
        "bout_count": bout_count,
        "total_walking_s": total_walking_s,
        "total_distance_m": total_walking_s * median_speed_m_s,
        "median_speed_m_s": median_speed_m_s,
        "mad_speed_m_s": 0.05,
        "p95_speed_m_s": median_speed_m_s + 0.2,
        "computed_at": datetime.now(UTC).isoformat(),
    }


def _make_56_days_of_rows(
    baseline_speed: float = 0.9,
    recent_speed: float = 0.9,
    n_per_half: int = 14,
) -> list[dict]:
    """Build rows covering a 56-day window with two distinct speed groups."""
    today = datetime.now(UTC).date()
    rows = []
    # Baseline half: days 28-55 ago
    for i in range(28, 28 + n_per_half):
        rows.append(_make_row(today - timedelta(days=i), median_speed_m_s=baseline_speed))
    # Recent half: days 1-27 ago
    for i in range(1, 1 + n_per_half):
        rows.append(_make_row(today - timedelta(days=i), median_speed_m_s=recent_speed))
    return rows


@pytest.fixture
def client_mock():
    return AsyncMock()


@pytest.fixture
def svc(client_mock):
    return GaitTrendService(client_mock)


@pytest.mark.asyncio
async def test_insufficient_when_not_enough_rows(svc, client_mock):
    """Returns trend=insufficient when fewer than 10 qualifying days in either window."""
    client_mock.list_gait_daily = AsyncMock(return_value=[])
    result = await svc.get_gait_trend("alice")
    assert isinstance(result, GaitTrendEnvelope)
    assert result.trend == "insufficient"
    assert result.baseline_median_m_s is None


@pytest.mark.asyncio
async def test_stable_when_no_decline(svc, client_mock):
    """Returns trend=stable when recent speed equals baseline speed."""
    rows = _make_56_days_of_rows(baseline_speed=0.9, recent_speed=0.9)
    client_mock.list_gait_daily = AsyncMock(return_value=rows)
    result = await svc.get_gait_trend("alice")
    assert result.trend == "stable"
    assert result.baseline_median_m_s == pytest.approx(0.9, abs=0.01)


@pytest.mark.asyncio
async def test_declining_when_large_drop(svc, client_mock):
    """Returns trend=declining when speed drops by more than 10 % of baseline."""
    rows = _make_56_days_of_rows(baseline_speed=0.9, recent_speed=0.68)
    client_mock.list_gait_daily = AsyncMock(return_value=rows)
    result = await svc.get_gait_trend("alice")
    assert result.trend == "declining"


@pytest.mark.asyncio
async def test_sufficient_flag_applied_correctly(svc, client_mock):
    """Days with < 3 bouts or < 60 s walking are marked sufficient=False."""
    today = datetime.now(UTC).date()
    rows = [
        _make_row(today - timedelta(days=5), bout_count=2, total_walking_s=100),  # insufficient
        _make_row(today - timedelta(days=6), bout_count=4, total_walking_s=40),  # insufficient
        _make_row(today - timedelta(days=7), bout_count=5, total_walking_s=120),  # sufficient
    ]
    client_mock.list_gait_daily = AsyncMock(return_value=rows)
    result = await svc.get_gait_trend("alice")
    by_date = {d.date: d for d in result.days}
    assert not by_date[(today - timedelta(days=5)).isoformat()].sufficient
    assert not by_date[(today - timedelta(days=6)).isoformat()].sufficient
    assert by_date[(today - timedelta(days=7)).isoformat()].sufficient


@pytest.mark.asyncio
async def test_insufficient_days_have_null_speed(svc, client_mock):
    """Insufficient days must carry median_speed_m_s=None (not a zero)."""
    today = datetime.now(UTC).date()
    rows = [_make_row(today - timedelta(days=5), bout_count=1, total_walking_s=30)]
    client_mock.list_gait_daily = AsyncMock(return_value=rows)
    result = await svc.get_gait_trend("alice")
    assert len(result.days) == 1
    assert result.days[0].median_speed_m_s is None


@pytest.mark.asyncio
async def test_contract_violation_returns_insufficient(svc, client_mock):
    """When CTS returns a non-list, the service returns trend=insufficient gracefully."""
    client_mock.list_gait_daily = AsyncMock(return_value={"error": "upstream failure"})
    result = await svc.get_gait_trend("alice")
    assert result.trend == "insufficient"
    assert result.days == []


@pytest.mark.asyncio
async def test_trend_boundary_just_below_threshold_is_stable(svc, client_mock):
    """A decline just below the floor does not trigger declining."""
    # 9 % decline when floor is 10 %: should be stable
    rows = _make_56_days_of_rows(baseline_speed=1.0, recent_speed=0.92)
    client_mock.list_gait_daily = AsyncMock(return_value=rows)
    result = await svc.get_gait_trend("alice")
    assert result.trend == "stable"
