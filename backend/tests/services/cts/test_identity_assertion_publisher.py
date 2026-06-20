"""WTR2: IdentityAssertionPublisher tests.

Tests that the CC-side publisher emits all required fields with the
expected stream name to cc.identity_assertions.
"""

from __future__ import annotations

from datetime import UTC, datetime
import math
from unittest.mock import AsyncMock

import pytest

from backend.services.cts.identity_assertion_publisher import (
    STREAM,
    IdentityAssertionPublisher,
)


from backend.integrations.proto.continuoustracking.v1.tracking_pb2 import CCIdentityAssertion

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
