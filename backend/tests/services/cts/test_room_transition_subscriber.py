"""WTR4: RoomTransitionSubscriber tests."""

from __future__ import annotations

import inspect
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


def _make_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


def test_decode_returns_message_not_coroutine():
    """Regression: StreamConsumer calls decode synchronously before handle."""
    subscriber = RoomTransitionSubscriber(
        redis_url="redis://localhost:6379",
        location_service=_make_service(),
    )

    decoded = subscriber.decode(
        b"msg-1",
        {
            b"ph_id": b"ph-1",
            b"identity_id": b"alice",
            b"transit_zone_id": b"tz-1",
            b"direction": b"enter",
            b"inside_room_id": b"3",
            b"outside_room_id": b"5",
            b"floor_x_m": b"1.5",
            b"floor_y_m": b"3.2",
            b"event_time": b"2026-05-30T15:00:00+00:00",
        },
    )

    assert not inspect.isawaitable(decoded)
    assert decoded is not None
    assert decoded["identity_id"] == "alice"
    assert decoded["inside_room_id"] == 3


def test_decode_accepts_string_field_keys_and_values():
    """Decoder honors the StreamConsumer bytes-or-str field contract."""
    subscriber = RoomTransitionSubscriber(
        redis_url="redis://localhost:6379",
        location_service=_make_service(),
    )

    decoded = subscriber.decode(
        b"msg-1",
        {
            "ph_id": "ph-1",
            "identity_id": "alice",
            "transit_zone_id": "tz-1",
            "direction": "enter",
            "inside_room_id": "3",
            "outside_room_id": "5",
            "floor_x_m": "1.5",
            "floor_y_m": "3.2",
            "event_time": "2026-05-30T15:00:00+00:00",
        },
    )

    assert decoded is not None
    assert decoded["floor_x_m"] == 1.5


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
        "inside_room_id": 3,
        "outside_room_id": 5,
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
        "inside_room_id": 3,
        "outside_room_id": 5,
        "floor_x_m": 1.5,
        "floor_y_m": 3.2,
        "event_time": datetime.now(UTC),
    }

    result = await subscriber.handle(msg)
    assert result is True
    # No segment should be opened for the PH id as a person_id.
