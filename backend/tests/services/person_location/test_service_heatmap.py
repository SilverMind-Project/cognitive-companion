"""PersonLocationService.get_heatmap() tests.

These exercise the service-level wiring that the repo/router/MCP tests do not:
the timezone is resolved from ``app.timezone`` settings and passed through to
the repository, and the minute-of-day bounds reach the repo unchanged.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from backend.services.person_location import service as service_module
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint, LocationObservation

_WINDOW_START = datetime(2024, 1, 15, 0, 0, tzinfo=UTC)
_WINDOW_END = datetime(2024, 1, 16, 0, 0, tzinfo=UTC)


def _make_service() -> tuple[PersonLocationService, InMemoryObservationRepository]:
    obs = InMemoryObservationRepository()
    svc = PersonLocationService(obs, InMemorySegmentRepository(), PersonLocationConfig())
    return svc, obs


async def _seed(obs: InMemoryObservationRepository, person_id: str, t: datetime) -> None:
    await obs.insert(
        LocationObservation(
            id=uuid.uuid4(),
            person_id=person_id,
            observed_at=t,
            source="world_tracker",
            floor_point=FloorPoint(x_m=1.0, y_m=1.0),
        )
    )


@pytest.mark.asyncio
async def test_get_heatmap_no_time_filter_returns_bins() -> None:
    """Success path: with no time-of-day filter the bin is returned and the
    response carries the requested person_id (exercises the settings read)."""
    svc, obs = _make_service()
    await _seed(obs, "alice", datetime(2024, 1, 15, 18, 0, tzinfo=UTC))

    env = await svc.get_heatmap("alice", _WINDOW_START, _WINDOW_END)

    assert env.person_id == "alice"
    assert len(env.bins) == 1


@pytest.mark.asyncio
async def test_get_heatmap_uses_app_timezone_for_local_window(monkeypatch) -> None:
    """The service resolves app.timezone and applies the minute window in that
    local time: 18:00 UTC is 23:30 in Asia/Kolkata, inside a 21:00-06:00 night
    window that wraps past midnight."""
    monkeypatch.setattr(service_module.settings, "as_str", lambda key: "Asia/Kolkata")
    svc, obs = _make_service()
    await _seed(obs, "alice", datetime(2024, 1, 15, 18, 0, tzinfo=UTC))

    env = await svc.get_heatmap(
        "alice",
        _WINDOW_START,
        _WINDOW_END,
        filter_start_minute=21 * 60,
        filter_end_minute=6 * 60,
    )

    assert len(env.bins) == 1


@pytest.mark.asyncio
async def test_get_heatmap_local_window_excludes_outside_buckets(monkeypatch) -> None:
    """Daytime bucket (06:00 UTC = 11:30 IST) is excluded by the night window."""
    monkeypatch.setattr(service_module.settings, "as_str", lambda key: "Asia/Kolkata")
    svc, obs = _make_service()
    await _seed(obs, "alice", datetime(2024, 1, 15, 6, 0, tzinfo=UTC))

    env = await svc.get_heatmap(
        "alice",
        _WINDOW_START,
        _WINDOW_END,
        filter_start_minute=21 * 60,
        filter_end_minute=6 * 60,
    )

    assert env.bins == []


@pytest.mark.asyncio
async def test_get_heatmap_empty_repo_returns_no_bins() -> None:
    """Edge case: a person with no observations yields an empty envelope."""
    svc, _ = _make_service()

    env = await svc.get_heatmap("nobody", _WINDOW_START, _WINDOW_END)

    assert env.person_id == "nobody"
    assert env.bins == []
