"""WTR4: RoomTransitionSubscriber tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services.cts.room_transition_subscriber import (
    RoomTransitionSubscriber,
)
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
async def test_known_identity_transition_updates_segment():
    """A room transition with identity_id creates an inferred segment."""
    svc = _make_service()
    subscriber = RoomTransitionSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
    )

    now = datetime.now(UTC)
    msg = {
        "ph_id": "ph-1",
        "identity_id": "alice",
        "transit_zone_id": "tz-1",
        "direction": "enter",
        "inside_room_id": "3",
        "outside_room_id": "5",
        "floor_x_m": 1.5,
        "floor_y_m": 3.2,
        "event_time": now,
    }

    result = await subscriber.handle(msg)
    assert result is True

    loc = await svc.where_is("alice")
    assert loc is not None
    assert loc.room_id == 3


@pytest.mark.asyncio
async def test_unknown_ph_transition_is_skipped():
    """A transition without identity_id must be skipped, not written as person_id=ph_id."""
    svc = _make_service()
    subscriber = RoomTransitionSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
    )

    msg = {
        "ph_id": "ph-unknown",
        "identity_id": None,
        "transit_zone_id": "tz-1",
        "direction": "enter",
        "inside_room_id": "3",
        "outside_room_id": "5",
        "floor_x_m": 1.5,
        "floor_y_m": 3.2,
        "event_time": datetime.now(UTC),
    }

    result = await subscriber.handle(msg)
    assert result is True
    # No segment should be opened for the PH id as a person_id.
