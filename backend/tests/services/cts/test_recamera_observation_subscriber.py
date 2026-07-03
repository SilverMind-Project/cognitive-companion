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
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService


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
