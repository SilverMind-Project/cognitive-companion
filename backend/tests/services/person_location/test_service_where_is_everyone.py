"""WTR4: PersonLocationService.where_is_everyone() tests."""
from __future__ import annotations

from datetime import UTC, datetime

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
async def test_multiple_open_segments_return_map_by_person_id():
    svc = _make_service()
    now = datetime.now(UTC)

    await svc.ingest_observation(
        person_id="alice", observed_at=now, source="world_tracker",
        source_ref="ph-1", floor_point=FloorPoint(x_m=1.0, y_m=2.0), room_id=1,
    )
    await svc.ingest_observation(
        person_id="bob", observed_at=now, source="world_tracker",
        source_ref="ph-2", floor_point=FloorPoint(x_m=3.0, y_m=4.0), room_id=2,
    )

    everyone = await svc.where_is_everyone()
    assert "alice" in everyone
    assert "bob" in everyone
    assert everyone["alice"].room_id == 1
    assert everyone["bob"].room_id == 2


@pytest.mark.asyncio
async def test_empty_when_no_open_segments():
    svc = _make_service()
    everyone = await svc.where_is_everyone()
    assert everyone == {}
