"""Tests for PersonLocationService.latest_floor_point()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint


def _make_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


@pytest.mark.asyncio
async def test_returns_recent_floor_point() -> None:
    svc = _make_service()

    await svc.ingest_observation(
        person_id="alice",
        observed_at=datetime.now(UTC),
        source="world_tracker",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=1,
    )

    point = await svc.latest_floor_point("alice")

    assert point == FloorPoint(x_m=1.0, y_m=2.0)


@pytest.mark.asyncio
async def test_returns_none_when_stale() -> None:
    svc = _make_service()

    await svc.ingest_observation(
        person_id="alice",
        observed_at=datetime.now(UTC) - timedelta(seconds=60),
        source="world_tracker",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=1,
    )

    assert await svc.latest_floor_point("alice", max_age_s=30) is None


@pytest.mark.asyncio
async def test_returns_none_when_no_floor_point() -> None:
    svc = _make_service()

    await svc.ingest_observation(
        person_id="alice",
        observed_at=datetime.now(UTC),
        source="manual",
        floor_point=None,
        room_id=1,
    )

    assert await svc.latest_floor_point("alice") is None


@pytest.mark.asyncio
async def test_where_is_unchanged() -> None:
    svc = _make_service()
    observed_at = datetime.now(UTC)

    await svc.ingest_observation(
        person_id="alice",
        observed_at=observed_at,
        source="world_tracker",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=3,
    )

    location = await svc.where_is("alice")

    assert location is not None
    assert location.person_id == "alice"
    assert location.room_id == 3
    assert location.since == observed_at
