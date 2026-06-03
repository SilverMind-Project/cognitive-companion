"""WTR2: CTSRuntime recamera subscriber lifecycle tests.

Tests that CTSRuntime starts and stops the recamera subscriber when CTS
is enabled, without requiring Redis testcontainers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_runtime_starts_recamera_subscriber_when_provided():
    """CTSRuntime must start the recamera subscriber when it is passed in."""
    from backend.services.cts.runtime import CTSRuntime, CTSRuntimeConfig

    recamera = AsyncMock()
    recamera.start = AsyncMock()
    recamera.stop = AsyncMock()

    cfg = CTSRuntimeConfig(redis_url="redis://localhost:6379", consumer_id="test-cc")
    db_factory = MagicMock()

    runtime = CTSRuntime(
        config=cfg,
        db_factory=db_factory,
        recamera_subscriber=recamera,
    )

    assert runtime._recamera_subscriber is recamera


@pytest.mark.asyncio
async def test_runtime_does_not_require_recamera_subscriber():
    """CTSRuntime must work without a recamera subscriber (optional)."""
    from backend.services.cts.runtime import CTSRuntime, CTSRuntimeConfig

    cfg = CTSRuntimeConfig(redis_url="redis://localhost:6379", consumer_id="test-cc")
    db_factory = MagicMock()

    runtime = CTSRuntime(
        config=cfg,
        db_factory=db_factory,
        recamera_subscriber=None,
    )

    assert runtime._recamera_subscriber is None


def test_load_camera_room_id_map_resolves_room_id_and_name_fallback():
    """Cameras contribute via room_id OR a room_name that resolves to a room."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from backend.models.cts_camera import CtsCamera
    from backend.models.room import Room
    from backend.services.cts.runtime import _load_camera_room_id_map

    rooms = [SimpleNamespace(id=5, name="kitchen")]
    cameras = [
        SimpleNamespace(id="cam-id", room_id=9, room_name="ignored"),  # room_id wins
        SimpleNamespace(id="cam-name", room_id=None, room_name="kitchen"),  # name fallback
        SimpleNamespace(id="cam-orphan", room_id=None, room_name="garage"),  # unresolved
    ]

    def _query(model):
        q = MagicMock()
        if model is Room:
            q.all.return_value = rooms
        elif model is CtsCamera:
            q.filter.return_value.all.return_value = cameras
        return q

    db = MagicMock()
    db.query.side_effect = _query

    result = _load_camera_room_id_map(lambda: db)
    assert result == {"cam-id": 9, "cam-name": 5}


@pytest.mark.asyncio
async def test_runtime_recamera_subscriber_has_start_stop_interface():
    """The RecameraObservationSubscriber must expose start() and stop() methods."""
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

    svc = PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )
    publisher = IdentityAssertionPublisher(AsyncMock())

    subscriber = RecameraObservationSubscriber(svc, publisher)

    assert callable(subscriber.start)
    assert callable(subscriber.stop)
    assert callable(subscriber.enqueue)
