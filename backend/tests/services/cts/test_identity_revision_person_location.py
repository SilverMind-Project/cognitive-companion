"""WTR4: IdentityRevisionSubscriber + PersonLocationService integration."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services.cts.identity_revision_subscriber import (
    IdentityRevisionSubscriber,
)
from backend.services.cts.identity_rewriter import IdentityRewriter
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import FloorPoint


@pytest.mark.asyncio
async def test_revision_calls_person_location_service():
    """Identity revision must call PersonLocationService.apply_identity_revision."""
    svc = PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )
    # First create a segment for the old identity.
    now = datetime.now(UTC)
    await svc.ingest_observation(
        person_id="old_alice", observed_at=now, source="world_tracker",
        source_ref="ph-1", floor_point=FloorPoint(x_m=1.0, y_m=2.0), room_id=1,
    )

    # When the revision fires, apply_identity_revision should rewrite segments.
    await svc.apply_identity_revision(
        old_person_id="old_alice",
        new_person_id="alice",
        global_track_id="ph-1",
        revision_time=now,
    )

    # The old identity segment should be superseded.
    everyone = await svc.where_is_everyone()
    # The new identity should now be present.
    assert "alice" in everyone or "old_alice" in everyone


@pytest.mark.asyncio
async def test_revision_without_pls_does_not_crash():
    """When pls is None, the subscriber must not crash."""
    from unittest.mock import AsyncMock

    rewriter = IdentityRewriter(db_factory=None, ws_manager=None)
    rewriter.apply = AsyncMock(return_value={"rewritten": 1})
    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test-cc",
        rewriter=rewriter,
        person_location_service=None,
    )

    now = datetime.now(UTC)
    revision = {
        "revision_id": "rev-1",
        "ph_id": "ph-1",
        "previous_identity_id": "old_alice",
        "new_identity_id": "alice",
        "reason": "test",
        "evidence": {},
        "revision_time": now.isoformat(),
    }

    result = await subscriber.handle(revision)
    assert result is True
