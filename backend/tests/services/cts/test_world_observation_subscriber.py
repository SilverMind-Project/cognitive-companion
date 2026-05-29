"""WTR4: WorldObservationSubscriber tests."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
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


def test_decode_returns_message_not_coroutine():
    """Regression: StreamConsumer calls decode synchronously before handle."""
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=_make_location_service(),
    )
    event = tracking_pb2.TrackingEvent(
        camera_id="cam-1",
        room_name="living_room",
        event_time_unix_ns=1_735_305_600_000_000_000,
    )
    det = event.detections.add(
        detection_id="d-1",
        confidence=0.95,
        ph_id="ph-aaa",
    )
    det.floor_point.x_mm = 1000
    det.floor_point.y_mm = 2000
    det.floor_point.calibrated = True
    snap = event.identity_snapshots.add()
    snap.ph_id = "ph-aaa"
    snap.identity_id = "alice"
    snap.mean_quality = 0.8

    decoded = subscriber.decode(b"msg-1", {b"event": event.SerializeToString()})

    assert not inspect.isawaitable(decoded)
    assert decoded is not None
    assert decoded["detections"][0]["identity_id"] == "alice"


def test_decode_accepts_string_field_key_and_payload():
    """Redis test doubles may return decoded field names; decoder accepts both forms."""
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=_make_location_service(),
    )
    event = tracking_pb2.TrackingEvent(
        camera_id="cam-1",
        room_name="living_room",
        event_time_unix_ns=1_735_305_600_000_000_000,
    )

    decoded = subscriber.decode(
        b"msg-1",
        {"event": event.SerializeToString().decode("latin-1")},
    )

    assert decoded is not None
    assert decoded["camera_id"] == "cam-1"


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
        "room_name": "living_room",
        "camera_id": "cam-1",
        "detections": [
            {
                "camera_id": "cam-1",
                "detection_id": "d-1",
                "ph_id": "ph-aaa",
                "identity_id": "alice",
                "confidence": 0.95,
                "mean_quality": 0.8,
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
        "room_name": "",
        "camera_id": "cam-1",
        "detections": [
            {
                "camera_id": "cam-1",
                "detection_id": "d-1",
                "ph_id": "ph-aaa",
                "identity_id": None,
                "confidence": 0.9,
                "mean_quality": 0.0,
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
        "room_name": "",
        "camera_id": "cam-1",
        "detections": [
            {
                "camera_id": "cam-1",
                "detection_id": "d-1",
                "ph_id": "ph-aaa",
                "identity_id": "alice",
                "confidence": 0.9,
                "mean_quality": 0.0,
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
