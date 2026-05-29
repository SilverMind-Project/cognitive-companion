"""WTR4: PHContinuationSubscriber tests."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from backend.services.cts.ph_continuation_subscriber import (
    PHContinuationSubscriber,
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


def test_decode_returns_message_not_coroutine():
    """Regression: StreamConsumer calls decode synchronously before handle."""
    subscriber = PHContinuationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=_make_service(),
    )

    decoded = subscriber.decode(
        b"msg-1",
        {
            b"predecessor_ph_id": b"ph-old",
            b"successor_ph_id": b"ph-new",
            b"predecessor_identity_id": b"alice",
        },
    )

    assert not inspect.isawaitable(decoded)
    assert decoded == {
        "predecessor_ph_id": "ph-old",
        "successor_ph_id": "ph-new",
        "predecessor_identity_id": "alice",
    }


def test_decode_accepts_string_field_keys_and_values():
    """Decoder honors the StreamConsumer bytes-or-str field contract."""
    subscriber = PHContinuationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=_make_service(),
    )

    decoded = subscriber.decode(
        b"msg-1",
        {
            "predecessor_ph_id": "ph-old",
            "successor_ph_id": "ph-new",
            "predecessor_identity_id": "alice",
        },
    )

    assert decoded == {
        "predecessor_ph_id": "ph-old",
        "successor_ph_id": "ph-new",
        "predecessor_identity_id": "alice",
    }


@pytest.mark.asyncio
async def test_continuation_does_not_coerce_person_id_to_uuid():
    """WTR4 regression: predecessor_identity_id is a string, not UUID."""
    svc = _make_service()
    subscriber = PHContinuationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
    )

    now = datetime.now(UTC)
    # Seed an inferred segment for the predecessor identity.
    await svc.ingest_observation(
        person_id="alice",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-old",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=1,
    )

    msg = {
        "predecessor_ph_id": "ph-old",
        "successor_ph_id": "ph-new",
        "predecessor_identity_id": "alice",
    }

    # Must not raise TypeError from UUID coercion.
    result = await subscriber.handle(msg)
    assert result is True


@pytest.mark.asyncio
async def test_no_continuation_without_identity():
    """Missing identity_id skips continuation."""
    svc = _make_service()
    subscriber = PHContinuationSubscriber(
        redis_url="redis://localhost:6379",
        location_service=svc,
    )

    msg = {
        "predecessor_ph_id": "ph-old",
        "successor_ph_id": "ph-new",
        "predecessor_identity_id": None,
    }

    result = await subscriber.handle(msg)
    assert result is True
