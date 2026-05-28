"""WTR4: WorldObservationSubscriber tests."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.cts.world_observation_subscriber import (
    WorldObservationSubscriber,
)
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService


def _make_location_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


@pytest.mark.asyncio
async def test_calibrated_identity_creates_observation_and_opens_segment():
    """A calibrated detection with identity creates a world_tracker observation."""
    svc = _make_location_service()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
        camera_room_map={"cam-1": "1"},  # room_id=1 from camera mapping
    )

    now = datetime.now(UTC)
    msg = {
        "event_time": now,
        "detections": [
            {
                "camera_id": "cam-1",
                "detection_id": "d-1",
                "ph_id": "ph-aaa",
                "identity_id": "alice",
                "confidence": 0.95,
                "floor_x_mm": 1000,
                "floor_y_mm": 2000,
                "room_name": "living_room",
                "calibrated": True,
            },
        ],
    }

    result = await subscriber.handle(msg)
    assert result is True

    loc = await svc.where_is("alice")
    assert loc is not None
    assert loc.person_id == "alice"


@pytest.mark.asyncio
async def test_unknown_identity_is_skipped():
    """Detection without identity_id must not open a segment."""
    svc = _make_location_service()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
    )

    msg = {
        "event_time": datetime.now(UTC),
        "detections": [
            {
                "camera_id": "cam-1",
                "detection_id": "d-1",
                "ph_id": "ph-aaa",
                "identity_id": None,
                "confidence": 0.9,
                "floor_x_mm": 1000,
                "floor_y_mm": 2000,
                "room_name": "",
                "calibrated": True,
            },
        ],
    }

    result = await subscriber.handle(msg)
    assert result is True


@pytest.mark.asyncio
async def test_floorpoint_keyword_is_y_m_not_y():
    """WTR4 regression: FloorPoint(x_m=..., y=...) would raise TypeError."""
    from backend.services.person_location.types import FloorPoint

    # This is the correct keyword: y_m
    fp = FloorPoint(x_m=1.5, y_m=3.2)
    assert fp.x_m == 1.5
    assert fp.y_m == 3.2


@pytest.mark.asyncio
async def test_uncalibrated_detection_is_skipped():
    """Uncalibrated detections must not be ingested."""
    svc = _make_location_service()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
    )

    msg = {
        "event_time": datetime.now(UTC),
        "detections": [
            {
                "camera_id": "cam-1",
                "detection_id": "d-1",
                "ph_id": "ph-aaa",
                "identity_id": "alice",
                "confidence": 0.9,
                "floor_x_mm": 0,
                "floor_y_mm": 0,
                "room_name": "",
                "calibrated": False,
            },
        ],
    }

    await subscriber.handle(msg)
    loc = await svc.where_is("alice")
    assert loc is None
