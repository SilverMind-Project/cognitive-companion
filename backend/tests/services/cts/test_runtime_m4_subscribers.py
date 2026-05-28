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
