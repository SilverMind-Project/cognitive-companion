"""WTR2: RecameraObservationSubscriber tests.

Tests that recamera events are correctly ingested into PersonLocationService
and published as identity assertions with all required fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.services.cts.identity_assertion_publisher import IdentityAssertionPublisher
from backend.services.cts.recamera_observation_subscriber import (
    RecameraObservationSubscriber,
)
from backend.services.cts.world_observation_subscriber import WorldObservationSubscriber
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
async def test_ingests_recamera_event_into_person_location():
    """A recamera event is written as a LocationObservation and published
    as an identity assertion."""
    svc = _make_service()
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    subscriber = RecameraObservationSubscriber(svc, publisher)
    now = datetime.now(UTC)

    event = {
        "person_id": "alice",
        "observed_at": now.isoformat(),
        "confidence": 0.92,
        "camera_id": "cam-1",
        "room_id": 3,
        "floor_x_m": 1.5,
        "floor_y_m": 3.2,
        "frame_id": "frame-abc",
        "event_type": "recamera_vlm",
    }

    await subscriber._handle(event)

    # PersonLocationService should have ingested the observation.
    result = await svc.where_is("alice")
    assert result is not None
    assert result.person_id == "alice"

    # Identity assertion should have been published.
    redis_mock.xadd.assert_called_once()
    fields = redis_mock.xadd.call_args[0][1]
    from backend.integrations.proto.continuoustracking.v1.tracking_pb2 import CCIdentityAssertion

    msg = CCIdentityAssertion.FromString(fields[b"assertion"])
    assert msg.person_id == "alice"
    assert msg.camera_id == "cam-1"
    import math

    assert math.isclose(msg.floor_x_m, 1.5, abs_tol=1e-5)
    assert math.isclose(msg.floor_y_m, 3.2, abs_tol=1e-5)


@pytest.mark.asyncio
async def test_missing_person_id_is_ignored():
    """An event without person_id must not be processed."""
    svc = _make_service()
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    subscriber = RecameraObservationSubscriber(svc, publisher)

    event = {
        "person_id": "",
        "observed_at": datetime.now(UTC).isoformat(),
        "confidence": 0.5,
        "camera_id": "cam-1",
    }

    await subscriber._handle(event)

    # No assertion should be published for empty person_id.
    redis_mock.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_publishes_identity_assertion_with_required_fields():
    """The identity assertion published from a recamera event includes all
    required fields: person_id, confidence, camera_id, captured_at,
    floor_x_m, floor_y_m."""
    svc = _make_service()
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    subscriber = RecameraObservationSubscriber(svc, publisher)
    now = datetime.now(UTC)

    event = {
        "person_id": "bob",
        "observed_at": now.isoformat(),
        "confidence": 0.88,
        "camera_id": "cam-2",
        "room_id": 5,
        "floor_x_m": 2.0,
        "floor_y_m": 4.0,
        "frame_id": "frame-xyz",
    }

    await subscriber._handle(event)

    redis_mock.xadd.assert_called_once()
    fields = redis_mock.xadd.call_args[0][1]

    assert b"assertion" in fields
    from backend.integrations.proto.continuoustracking.v1.tracking_pb2 import CCIdentityAssertion

    msg = CCIdentityAssertion.FromString(fields[b"assertion"])

    assert msg.person_id == "bob"
    assert msg.camera_id == "cam-2"
    import math

    assert math.isclose(msg.floor_x_m, 2.0, abs_tol=1e-5)
    assert math.isclose(msg.floor_y_m, 4.0, abs_tol=1e-5)
    assert msg.captured_at_unix_ns > 0


@pytest.mark.asyncio
async def test_event_without_floor_data_ingests_none():
    """G15: an event with no floor coordinates must never fabricate (0, 0).

    Absence of floor data must produce floor_point=None, matching the
    NOT NULL gating that latest_floor_point / zone lookup rely on.
    """
    svc = _make_service()
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    subscriber = RecameraObservationSubscriber(svc, publisher)

    event = {
        "person_id": "carol",
        "observed_at": datetime.now(UTC).isoformat(),
        "confidence": 0.8,
        "camera_id": "cam-3",
        "room_id": 2,
        "frame_id": "frame-no-floor",
        # No floor_x_m / floor_y_m: this must not default to 0.0.
    }

    await subscriber._handle(event)

    assert await svc.latest_floor_point("carol") is None

    redis_mock.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_event_with_floor_data_ingests_point():
    """A legitimate (0.0, 0.0) coordinate pair, when actually present in the
    event, must still be ingested: the absence check must not drop zeros."""
    svc = _make_service()
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    subscriber = RecameraObservationSubscriber(svc, publisher)

    event = {
        "person_id": "dave",
        "observed_at": datetime.now(UTC).isoformat(),
        "confidence": 0.8,
        "camera_id": "cam-4",
        "room_id": 2,
        "floor_x_m": 0.0,
        "floor_y_m": 0.0,
        "frame_id": "frame-zero-floor",
    }

    await subscriber._handle(event)

    fp = await svc.latest_floor_point("dave")
    assert fp is not None
    assert fp.x_m == 0.0
    assert fp.y_m == 0.0


@pytest.mark.asyncio
async def test_zone_lookup_unaffected_by_recamera_identification():
    """A calibrated world-tracker floor point must remain the freshest floor
    point (what ZoneService.current_zone reads) even after a subsequent,
    floorless reCamera identification for the same person."""
    svc = _make_service()

    # Seed a calibrated world-tracker observation with a real floor point.
    await svc.ingest_observation(
        person_id="erin",
        observed_at=datetime.now(UTC),
        source="world_tracker",
        source_ref="ph-erin-1",
        floor_point=FloorPoint(x_m=1.2, y_m=3.4),
        room_id=1,
        confidence=0.9,
    )

    # A floorless reCamera identification for the same person follows.
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)
    subscriber = RecameraObservationSubscriber(svc, publisher)

    await subscriber._handle(
        {
            "person_id": "erin",
            "observed_at": datetime.now(UTC).isoformat(),
            "confidence": 0.7,
            "camera_id": "cam-5",
            "room_id": 1,
            "frame_id": "frame-erin-recamera",
        }
    )

    # latest_floor_point (what current_zone reads) still returns the
    # calibrated world-tracker point: the floorless observation is excluded
    # by the NOT NULL floor-point filter, never masquerading as (0, 0).
    fp = await svc.latest_floor_point("erin")
    assert fp is not None
    assert fp.x_m == 1.2
    assert fp.y_m == 3.4


@pytest.mark.asyncio
async def test_floor_gating_parity_with_world_observation_subscriber():
    """Parity guard: both ingestion paths gate floor points on real-data
    presence, never on a fabricated default, so the next ingest path added
    has a template to copy."""
    recamera_svc = _make_service()
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    recamera_subscriber = RecameraObservationSubscriber(
        recamera_svc, IdentityAssertionPublisher(redis_mock)
    )

    world_svc = _make_service()
    world_subscriber = WorldObservationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=world_svc,
        camera_room_id_map={"cam-1": 1},
    )

    # Recamera: no floor data in the event.
    await recamera_subscriber._handle(
        {
            "person_id": "frank",
            "observed_at": datetime.now(UTC).isoformat(),
            "confidence": 0.7,
            "camera_id": "cam-6",
            "room_id": 1,
            "frame_id": "frame-frank",
        }
    )

    # World tracker: uncalibrated detection (the equivalent of "no real floor
    # data" in that pipeline).
    await world_subscriber.handle(
        {
            "event_time": datetime.now(UTC),
            "room_name": "living_room",
            "camera_id": "cam-1",
            "detections": [
                {
                    "camera_id": "cam-1",
                    "detection_id": "d-1",
                    "ph_id": "ph-frank",
                    "identity_id": "frank",
                    "confidence": 0.9,
                    "mean_quality": 0.8,
                    "floor_x_mm": 1000,
                    "floor_y_mm": 2000,
                    "room_name": "living_room",
                    "calibrated": False,
                }
            ],
        }
    )

    assert await recamera_svc.latest_floor_point("frank") is None
    assert await world_svc.latest_floor_point("frank") is None
