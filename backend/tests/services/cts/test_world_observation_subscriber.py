"""WTR4: WorldObservationSubscriber tests."""

from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime

import pytest

from backend.integrations.proto.continuoustracking.v1 import tracking_pb2
from backend.services.cts.world_observation_subscriber import (
    WorldObservationSubscriber,
)
from backend.services.occupancy import OccupancyReadModel
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


def _det(
    *,
    ph_id: str,
    identity_id: str | None,
    calibrated: bool,
    camera_id: str = "cam-1",
    room_name: str = "living_room",
) -> dict:
    return {
        "camera_id": camera_id,
        "detection_id": "d-1",
        "ph_id": ph_id,
        "identity_id": identity_id,
        "confidence": 0.95,
        "mean_quality": 0.8,
        "floor_x_mm": 1000,
        "floor_y_mm": 2000,
        "room_name": room_name,
        "calibrated": calibrated,
    }


def _msg(detections: list[dict], *, camera_id: str = "cam-1") -> dict:
    return {
        "event_time": datetime.now(UTC),
        "room_name": "living_room",
        "camera_id": camera_id,
        "detections": detections,
    }


@pytest.mark.asyncio
async def test_calibrated_identity_creates_observation_and_opens_segment():
    """A calibrated detection with identity creates a world_tracker observation."""
    svc = _make_location_service()
    occupancy = OccupancyReadModel()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
        camera_room_id_map={"cam-1": 1},
        occupancy=occupancy,
    )

    await subscriber.handle(_msg([_det(ph_id="ph-aaa", identity_id="alice", calibrated=True)]))

    loc = await svc.where_is("alice")
    assert loc is not None
    assert loc.person_id == "alice"
    assert loc.room_id == 1
    records = await occupancy.get_occupancy()
    assert records[0].person_ids == ["alice"]


@pytest.mark.asyncio
async def test_uncalibrated_identified_still_opens_room_segment():
    """Plan case (a): uncalibrated + identified -> segment with room from camera map.

    The calibration gate was removed: room membership comes from the camera
    map regardless of calibration. Only floor coordinates require calibration.
    """
    svc = _make_location_service()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
        camera_room_id_map={"cam-1": 7},
    )

    await subscriber.handle(_msg([_det(ph_id="ph-aaa", identity_id="alice", calibrated=False)]))

    loc = await svc.where_is("alice")
    assert loc is not None
    assert loc.room_id == 7


@pytest.mark.asyncio
async def test_unknown_ph_records_occupancy_only_no_segment():
    """Plan case (b): unknown PH -> occupancy only, no segment."""
    svc = _make_location_service()
    occupancy = OccupancyReadModel()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
        camera_room_id_map={"cam-1": 3},
        occupancy=occupancy,
    )

    await subscriber.handle(_msg([_det(ph_id="ph-zzz", identity_id=None, calibrated=True)]))

    assert await svc.where_is_everyone() == {}
    records = await occupancy.get_occupancy()
    assert len(records) == 1
    assert records[0].room_id == 3
    assert records[0].person_ids == []
    assert records[0].unknown_count == 1


@pytest.mark.asyncio
async def test_unmapped_camera_is_logged_skip_not_silent(caplog):
    """Plan case (c): empty camera map -> logged skip, not silent."""
    svc = _make_location_service()
    occupancy = OccupancyReadModel()
    subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
        camera_room_id_map={},  # no room for any camera
        occupancy=occupancy,
    )

    with caplog.at_level(logging.WARNING):
        await subscriber.handle(_msg([_det(ph_id="ph-aaa", identity_id="alice", calibrated=True)]))

    assert await svc.where_is("alice") is None
    assert await occupancy.get_occupancy() == []
    assert "world_observation_unmapped_camera" in caplog.text


@pytest.mark.asyncio
async def test_floorpoint_keyword_is_y_m_not_y():
    """WTR4 regression: FloorPoint(x_m=..., y=...) would raise TypeError."""
    from backend.services.person_location.types import FloorPoint

    # This is the correct keyword: y_m
    fp = FloorPoint(x_m=1.5, y_m=3.2)
    assert fp.x_m == 1.5
    assert fp.y_m == 3.2
