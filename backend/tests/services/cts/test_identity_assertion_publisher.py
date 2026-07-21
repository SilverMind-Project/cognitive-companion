"""WTR2: IdentityAssertionPublisher tests.

Tests that the CC-side publisher emits all required fields with the
expected stream name to cc.identity_assertions.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.integrations.proto.continuoustracking.v1.tracking_pb2 import CCIdentityAssertion
from backend.services.cts.identity_assertion_publisher import (
    STREAM,
    IdentityAssertionPublisher,
)


@pytest.mark.asyncio
async def test_publisher_emits_all_required_fields():
    """publish() must send person_id, confidence, camera_id, captured_at,
    floor_x_m, and floor_y_m via protobuf to the cc.identity_assertions stream."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()

    publisher = IdentityAssertionPublisher(redis_mock)
    now = datetime.now(UTC)

    await publisher.publish(
        person_id="alice",
        confidence=0.92,
        camera_id="cam-1",
        captured_at=now,
        floor_x_m=1.5,
        floor_y_m=3.2,
        raw_similarity=0.88,
        calibrated_confidence=0.92,
    )

    redis_mock.xadd.assert_called_once()
    call_args = redis_mock.xadd.call_args
    # First positional arg is the stream name.
    assert call_args[0][0] == STREAM
    # Second arg is the fields dict.
    fields = call_args[0][1]

    assert b"assertion" in fields
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])

    assert msg.person_id == "alice"
    assert msg.camera_id == "cam-1"
    assert math.isclose(msg.floor_x_m, 1.5, abs_tol=1e-5)
    assert math.isclose(msg.floor_y_m, 3.2, abs_tol=1e-5)
    assert math.isclose(msg.raw_similarity, 0.88, abs_tol=1e-5)
    assert math.isclose(msg.calibrated_confidence, 0.92, abs_tol=1e-5)
    assert msg.captured_at_unix_ns == int(now.timestamp() * 1e9)


@pytest.mark.asyncio
async def test_publisher_defaults_captured_at_to_now():
    """When captured_at is None, the publisher uses datetime.now(UTC)."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()

    publisher = IdentityAssertionPublisher(redis_mock)

    await publisher.publish(
        person_id="bob",
        confidence=0.8,
    )

    redis_mock.xadd.assert_called_once()
    fields = redis_mock.xadd.call_args[0][1]
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])

    assert msg.person_id == "bob"
    assert msg.captured_at_unix_ns > 0


@pytest.mark.asyncio
async def test_publisher_handles_xadd_failure_gracefully():
    """A Redis xadd failure must not raise — it logs and continues."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock(side_effect=RuntimeError("connection lost"))

    publisher = IdentityAssertionPublisher(redis_mock)

    # Must not raise.
    await publisher.publish(
        person_id="carol",
        confidence=0.75,
    )


@pytest.mark.asyncio
async def test_publisher_no_coordinates_produces_has_floor_point_false():
    """Identity-continuity M09: omitting floor_x_m/floor_y_m must never
    fabricate (0, 0) as a real position (CC-M28/G15)."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    await publisher.publish(
        person_id="dave",
        confidence=0.9,
        camera_id="recamera_kitchen",
        room_name="Kitchen",
    )

    fields = redis_mock.xadd.call_args[0][1]
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])
    assert msg.has_floor_point is False
    assert msg.room_name == "Kitchen"


@pytest.mark.asyncio
async def test_publisher_both_coordinates_produces_has_floor_point_true():
    """Both floor coordinates present sets has_floor_point=True."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    await publisher.publish(
        person_id="erin",
        confidence=0.9,
        floor_x_m=0.0,
        floor_y_m=0.0,
    )

    fields = redis_mock.xadd.call_args[0][1]
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])
    assert msg.has_floor_point is True
    assert msg.floor_x_m == 0.0
    assert msg.floor_y_m == 0.0


@pytest.mark.asyncio
async def test_publisher_yaw_and_quality_presence_flags():
    """yaw_deg/quality set their has_* flags only when provided."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    await publisher.publish(person_id="frank", confidence=0.9, yaw_deg=12.0, quality=0.6)

    fields = redis_mock.xadd.call_args[0][1]
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])
    assert msg.has_yaw is True
    assert math.isclose(msg.yaw_deg, 12.0, abs_tol=1e-4)
    assert msg.has_quality is True
    assert math.isclose(msg.quality, 0.6, abs_tol=1e-4)


@pytest.mark.asyncio
async def test_publisher_yaw_and_quality_absent_flags_unset():
    """Omitting yaw_deg/quality leaves their has_* flags unset."""
    redis_mock = AsyncMock()
    redis_mock.xadd = AsyncMock()
    publisher = IdentityAssertionPublisher(redis_mock)

    await publisher.publish(person_id="grace", confidence=0.9)

    fields = redis_mock.xadd.call_args[0][1]
    msg = CCIdentityAssertion.FromString(fields[b"assertion"])
    assert msg.has_yaw is False
    assert msg.has_quality is False
