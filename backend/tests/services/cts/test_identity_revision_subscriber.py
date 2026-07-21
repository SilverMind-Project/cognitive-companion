"""Tests for IdentityRevisionSubscriber WS broadcast."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.services.cts.identity_revision_subscriber import IdentityRevisionSubscriber
from backend.services.cts.signal_rewriter import SignalRewriter
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import BackfillDwellInput


@pytest.mark.asyncio
async def test_handle_broadcasts_cts_ph_correction_when_ws_manager_provided():
    ws_manager = AsyncMock()
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 1}

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        ws_manager=ws_manager,
    )
    revision = {
        "revision_id": "rev-1",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "manual_correct",
        "evidence": {},
        "revision_time": "2026-01-01T12:00:00Z",
    }
    result = await subscriber.handle(revision)
    assert result is True
    ws_manager.broadcast.assert_called_once()
    payload = ws_manager.broadcast.call_args.args[0]
    assert payload["type"] == "cts_ph_correction"
    assert payload["revision_id"] == "rev-1"
    assert payload["ph_id"] == "ph-1"


@pytest.mark.asyncio
async def test_handle_no_broadcast_when_ws_manager_is_none():
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 0}
    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        ws_manager=None,
    )
    revision = {
        "revision_id": "rev-2",
        "ph_id": "ph-2",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "reason": "auto",
        "evidence": {},
        "revision_time": "2026-01-01T12:00:00Z",
    }
    result = await subscriber.handle(revision)
    assert result is True  # no crash


@pytest.mark.asyncio
async def test_handle_posts_projection_ack_when_cc_required():
    """M06: a revision requiring the cc projection acks back to CTS on success."""
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 3, "inserted": 3}
    orchestrator = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        orchestrator_client=orchestrator,
    )
    revision = {
        "revision_id": "rev-ack",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "operator_correction",
        "evidence": {},
        "revision_time": "2026-06-20T12:00:00Z",
        "required_projections": ["cts_internal", "cc"],
        "revision_schema_version": "1",
    }
    result = await subscriber.handle(revision)
    assert result is True
    orchestrator.post_projection_ack.assert_called_once()
    kwargs = orchestrator.post_projection_ack.call_args.kwargs
    assert kwargs["revision_id"] == "rev-ack"
    assert kwargs["consumer"] == "cc"
    assert kwargs["status"] == "acked"
    assert kwargs["counts"] == {"rewritten": 3, "inserted": 3}


@pytest.mark.asyncio
async def test_handle_skips_ack_for_legacy_revision_without_required_projections():
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 1}
    orchestrator = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        orchestrator_client=orchestrator,
    )
    revision = {
        "revision_id": "rev-legacy",
        "ph_id": "ph-1",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "reason": "auto",
        "evidence": {},
        "revision_time": "2026-06-20T12:00:00Z",
        "required_projections": [],
    }
    await subscriber.handle(revision)
    orchestrator.post_projection_ack.assert_not_called()


@pytest.mark.asyncio
async def test_handle_supersedes_a_real_segment_through_a_real_person_location_service(
    db_factory,
):
    """Non-mock proof of the M05 wiring fix: driving a real (non-backfill)
    revision through the subscriber, with a real PersonLocationService (not
    an AsyncMock), actually supersedes the matching segment. The mock-based
    test above only proves the subscriber *calls* apply_identity_revision;
    this proves the call chain has a real effect end to end, including
    against a backfilled segment (the supersession-interaction path M05's
    design describes).
    """
    db = db_factory()
    try:
        db.add(Room(id=1, name="kitchen"))
        db.add(HouseholdMember(id="alice", name="Alice"))
        db.commit()
    finally:
        db.close()

    now = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
    later = now + timedelta(minutes=1)
    location_service = PersonLocationService(
        InMemoryObservationRepository(), InMemorySegmentRepository(), PersonLocationConfig()
    )
    # Seed a backfilled segment (the supersession-interaction case's
    # design specifically calls out), not just an ordinary live one.
    await location_service.ingest_backfill_segments(
        revision_id="rev-original-backfill",
        person_id="alice",
        dwells=[
            BackfillDwellInput(
                room_id=1, room_name="kitchen", entered_at=now, exited_at=later, confidence=0.8
            )
        ],
        range_start=now,
        range_end=later,
    )
    [seg_before] = await location_service.room_segments("alice", now, later)
    assert seg_before.person_id == "alice"

    rewriter = SignalRewriter(db_factory=db_factory)
    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter,
        person_location_service=location_service,
    )
    revision = {
        "revision_id": "rev-operator-correct",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "operator_correction",
        "evidence": {},
        "revision_time": now.isoformat(),
    }

    result = await subscriber.handle(revision)

    assert result is True
    alice_segments = await location_service.room_segments("alice", now, later)
    assert alice_segments == ()  # superseded, excluded from the read model
    bob_segments = await location_service.room_segments("bob", now, later)
    assert len(bob_segments) == 1
    assert bob_segments[0].room_name == "kitchen"


@pytest.mark.asyncio
async def test_handle_applies_generic_supersession_to_person_location_service():
    """Non-backfill revisions still reach PersonLocationService.apply_identity_revision.

    identity-continuity M05 fix: this wiring existed in the subscriber but
    was never passed a real ``person_location_service`` from ``runtime.py``,
    so it never executed in production. Confirmed live here now that
    ``CTSRuntime`` passes it through.
    """
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.return_value = {"rewritten": 2}
    pls_mock = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        person_location_service=pls_mock,
    )
    revision = {
        "revision_id": "rev-super",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "operator_correction",
        "evidence": {},
        "revision_time": "2026-07-20T12:00:00Z",
    }

    result = await subscriber.handle(revision)

    assert result is True
    pls_mock.apply_identity_revision.assert_called_once()
    kwargs = pls_mock.apply_identity_revision.call_args.kwargs
    assert kwargs["old_person_id"] == "alice"
    assert kwargs["new_person_id"] == "bob"
    assert kwargs["ph_id"] == "ph-1"


@pytest.mark.asyncio
async def test_handle_routes_inferred_backfill_to_projector_bypassing_rewriter():
    """identity-continuity M05: an inferred_backfill revision never reaches
    the rewriter, the generic PersonLocationService supersession call, the
    pipeline event, or the WS broadcast below it -- the projector owns all
    of that for this revision kind.
    """
    rewriter_mock = AsyncMock()
    pls_mock = AsyncMock()
    pipeline_mock = AsyncMock()
    ws_mock = AsyncMock()
    projector_mock = AsyncMock()
    projector_mock.project.return_value = True

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        pipeline=pipeline_mock,
        ws_manager=ws_mock,
        person_location_service=pls_mock,
        backfill_projector=projector_mock,
    )
    revision = {
        "revision_id": "rev-backfill",
        "ph_id": "ph-1",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "revision_kind": "inferred_backfill",
        "range_start": "2026-07-20T06:00:00Z",
        "range_end": "2026-07-20T09:00:00Z",
        "required_projections": ["cc"],
    }

    result = await subscriber.handle(revision)

    assert result is True
    projector_mock.project.assert_called_once_with(revision)
    rewriter_mock.apply.assert_not_called()
    pls_mock.apply_identity_revision.assert_not_called()
    pipeline_mock.fire_event.assert_not_called()
    ws_mock.broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_handle_inferred_backfill_without_projector_retries():
    rewriter_mock = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        backfill_projector=None,
    )
    revision = {
        "revision_id": "rev-backfill",
        "ph_id": "ph-1",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "revision_kind": "inferred_backfill",
    }

    result = await subscriber.handle(revision)

    assert result is False
    rewriter_mock.apply.assert_not_called()


@pytest.mark.asyncio
async def test_handle_posts_failed_ack_when_rewriter_raises():
    rewriter_mock = AsyncMock()
    rewriter_mock.apply.side_effect = RuntimeError("boom")
    orchestrator = AsyncMock()

    subscriber = IdentityRevisionSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test",
        rewriter=rewriter_mock,
        orchestrator_client=orchestrator,
    )
    revision = {
        "revision_id": "rev-fail",
        "ph_id": "ph-1",
        "previous_identity_id": "alice",
        "new_identity_id": "bob",
        "reason": "operator_correction",
        "evidence": {},
        "revision_time": "2026-06-20T12:00:00Z",
        "required_projections": ["cts_internal", "cc"],
    }
    result = await subscriber.handle(revision)
    assert result is False
    orchestrator.post_projection_ack.assert_called_once()
    assert orchestrator.post_projection_ack.call_args.kwargs["status"] == "failed"
