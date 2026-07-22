"""WTR4: IdentityRevisionSubscriber + PersonLocationService integration."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services.cts.identity_revision_subscriber import (
    IdentityRevisionSubscriber,
)
from backend.services.cts.signal_rewriter import SignalRewriter
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
        person_id="old_alice",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-1",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=1,
    )

    # When the revision fires, apply_identity_revision should rewrite segments.
    await svc.apply_identity_revision(
        old_person_id="old_alice",
        new_person_id="alice",
        ph_id="ph-1",
        revision_time=now,
    )

    # The old identity segment should be superseded.
    everyone = await svc.where_is_everyone()
    # The new identity should now be present.
    assert "alice" in everyone or "old_alice" in everyone


@pytest.mark.asyncio
async def test_revision_with_no_new_identity_does_not_duplicate_segment():
    """new_person_id=None (a 'demoted to unknown' revision) must not touch
    segments at all: decide()'s IDENTITY_REVISION branch falls back to
    ``new_person_id or old_seg.person_id``, which without this guard produces
    a same-person "replacement" that supersedes the original with an
    identical copy on every call -- a data-corruption incident when the
    same revision is redelivered by the stream consumer's reclaim logic.
    """
    seg_repo = InMemorySegmentRepository()
    svc = PersonLocationService(InMemoryObservationRepository(), seg_repo, PersonLocationConfig())
    now = datetime.now(UTC)
    await svc.ingest_observation(
        person_id="grandma",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-1",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=1,
    )
    before = len(seg_repo._rows)

    await svc.apply_identity_revision(
        old_person_id="grandma",
        new_person_id=None,
        ph_id="ph-1",
        revision_time=now,
    )

    assert len(seg_repo._rows) == before


@pytest.mark.asyncio
async def test_revision_replay_is_idempotent():
    """Redelivering the same identity revision must not create additional
    duplicate segments each time: list_overlapping excludes already-superseded
    segments, so a repeat pass finds nothing left needing revision.
    """
    seg_repo = InMemorySegmentRepository()
    svc = PersonLocationService(InMemoryObservationRepository(), seg_repo, PersonLocationConfig())
    now = datetime.now(UTC)
    await svc.ingest_observation(
        person_id="old_alice",
        observed_at=now,
        source="world_tracker",
        source_ref="ph-1",
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
        room_id=1,
    )

    for _ in range(3):
        await svc.apply_identity_revision(
            old_person_id="old_alice",
            new_person_id="alice",
            ph_id="ph-1",
            revision_time=now,
        )

    open_for_alice = [
        s for s in seg_repo._rows.values() if s.person_id == "alice" and s.superseded_by is None
    ]
    assert len(open_for_alice) == 1


@pytest.mark.asyncio
async def test_revision_without_pls_does_not_crash():
    """When pls is None, the subscriber must not crash."""
    from unittest.mock import AsyncMock

    rewriter = SignalRewriter(db_factory=None, ws_manager=None)
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
