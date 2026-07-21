"""BackfillProjector tests (identity-continuity M05).

Projects an ``inferred_backfill`` IdentityRevision into closed
PersonLocationService presence segments: fetch dwells from CTS (mocked
orchestrator client), resolve rooms, insert segments, write the audit log,
broadcast, and ack. Uses the real ``db_factory`` testcontainer for Room /
HouseholdMember / CtsIdentityRevisionLog (schema-backed invariants), and an
InMemory-backed PersonLocationService for segment writes (fast, no
migration dependency for the segment tables beyond what create_all() sets
up from the ORM models).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.core.upstream_errors import UpstreamUnavailable
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.services.cts.backfill_projector import BackfillProjector
from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService

_RANGE_START = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
_RANGE_END = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def _seed_room(db_factory, *, room_id: int = 1, name: str = "kitchen") -> None:
    db = db_factory()
    try:
        db.add(Room(id=room_id, name=name))
        db.commit()
    finally:
        db.close()


def _make_projector(
    db_factory,
    *,
    orchestrator: AsyncMock,
    location_service: PersonLocationService | None = None,
    ws_manager: AsyncMock | None = None,
) -> tuple[BackfillProjector, PersonLocationService]:
    svc = location_service or PersonLocationService(
        InMemoryObservationRepository(), InMemorySegmentRepository(), PersonLocationConfig()
    )
    projector = BackfillProjector(
        db_factory=db_factory,
        orchestrator_client=orchestrator,
        person_location_service=svc,
        ws_manager=ws_manager,
    )
    return projector, svc


def _revision(**overrides) -> dict:
    base = {
        "revision_id": "rev-backfill-1",
        "ph_id": "ph-1",
        "previous_identity_id": None,
        "new_identity_id": "alice",
        "revision_kind": "inferred_backfill",
        "range_start": _RANGE_START.isoformat(),
        "range_end": _RANGE_END.isoformat(),
        "required_projections": ["cc"],
        "revision_schema_version": "1",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_inserts_rows_for_dwells_and_acks(db_factory):
    _seed_room(db_factory, room_id=1, name="kitchen")
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {
        "dwells": [
            {
                "room_name": "kitchen",
                "entered_at": _RANGE_START.isoformat(),
                "exited_at": _RANGE_END.isoformat(),
                "identity_id": None,
                "ph_id": "ph-1",
                "entry_confidence": 0.8,
            }
        ]
    }
    projector, svc = _make_projector(db_factory, orchestrator=orchestrator)

    ok = await projector.project(_revision())

    assert ok is True
    segments = await svc.room_segments("alice", _RANGE_START, _RANGE_END)
    assert len(segments) == 1
    assert segments[0].room_name == "kitchen"
    assert segments[0].entry_source == "observed"
    assert segments[0].exit_source == "observed"
    assert segments[0].confidence == 0.8

    orchestrator.post_projection_ack.assert_called_once()
    ack_kwargs = orchestrator.post_projection_ack.call_args.kwargs
    assert ack_kwargs["revision_id"] == "rev-backfill-1"
    assert ack_kwargs["consumer"] == "cc"
    assert ack_kwargs["status"] == "acked"
    assert ack_kwargs["counts"] == {"inserted": 1}

    db = db_factory()
    try:
        log_row = db.get(CtsIdentityRevisionLog, "rev-backfill-1")
        assert log_row is not None
        assert log_row.kind == "inferred_backfill"
        assert log_row.new_identity_id == "alice"
        assert log_row.previous_identity_id is None
        assert log_row.rewritten_rows == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_redelivery_is_idempotent(db_factory):
    _seed_room(db_factory, room_id=1, name="kitchen")
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {
        "dwells": [
            {
                "room_name": "kitchen",
                "entered_at": _RANGE_START.isoformat(),
                "exited_at": _RANGE_END.isoformat(),
                "identity_id": None,
                "ph_id": "ph-1",
                "entry_confidence": 0.8,
            }
        ]
    }
    projector, svc = _make_projector(db_factory, orchestrator=orchestrator)

    first = await projector.project(_revision())
    second = await projector.project(_revision())

    assert first is True
    assert second is True
    segments = await svc.room_segments("alice", _RANGE_START, _RANGE_END)
    assert len(segments) == 1  # not doubled
    assert orchestrator.post_projection_ack.call_count == 2  # acked both times
    # The second call short-circuits before ever fetching dwells again.
    assert orchestrator.list_room_dwells.call_count == 1


@pytest.mark.asyncio
async def test_malformed_revision_dropped_and_acked(db_factory):
    orchestrator = AsyncMock()
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator)

    ok = await projector.project({"revision_kind": "inferred_backfill"})  # missing required fields

    assert ok is True  # poison message: ack, don't retry forever
    orchestrator.list_room_dwells.assert_not_called()
    # No revision_id anywhere in the payload: no CTS job exists to unstick.
    orchestrator.post_projection_ack.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_revision_with_a_revision_id_still_gets_a_failed_ack(db_factory):
    """A revision_id survives even when the rest of the payload is malformed
    (e.g. an unparseable range). Without a failed ack, CTS's projection job
    for that revision_id would stay 'applying' forever.
    """
    orchestrator = AsyncMock()
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator)

    ok = await projector.project(
        {
            "revision_id": "rev-bad-range",
            "ph_id": "ph-1",
            "new_identity_id": "alice",
            "revision_kind": "inferred_backfill",
            "range_start": "not-a-timestamp",
            "range_end": "not-a-timestamp",
        }
    )

    assert ok is True
    orchestrator.list_room_dwells.assert_not_called()
    orchestrator.post_projection_ack.assert_called_once()
    assert orchestrator.post_projection_ack.call_args.kwargs["revision_id"] == "rev-bad-range"
    assert orchestrator.post_projection_ack.call_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_revision_with_previous_identity_dropped_and_acked(db_factory):
    orchestrator = AsyncMock()
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator)

    ok = await projector.project(_revision(previous_identity_id="bob"))

    assert ok is True
    orchestrator.list_room_dwells.assert_not_called()
    orchestrator.post_projection_ack.assert_called_once()
    assert orchestrator.post_projection_ack.call_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_upstream_failure_raises_for_retry_no_ack(db_factory):
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.side_effect = UpstreamUnavailable("tracking_orchestrator", 503)
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator)

    with pytest.raises(UpstreamUnavailable):
        await projector.project(_revision())

    orchestrator.post_projection_ack.assert_not_called()


@pytest.mark.asyncio
async def test_zero_dwells_inserts_nothing_still_acks(db_factory):
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {"dwells": []}
    projector, svc = _make_projector(db_factory, orchestrator=orchestrator)

    ok = await projector.project(_revision())

    assert ok is True
    segments = await svc.room_segments("alice", _RANGE_START, _RANGE_END)
    assert segments == ()
    orchestrator.post_projection_ack.assert_called_once()
    assert orchestrator.post_projection_ack.call_args.kwargs["counts"] == {"inserted": 0}


@pytest.mark.asyncio
async def test_overlap_with_live_row_skipped(db_factory):
    _seed_room(db_factory, room_id=1, name="kitchen")
    _seed_room(db_factory, room_id=2, name="bedroom")
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {
        "dwells": [
            {
                "room_name": "kitchen",
                "entered_at": _RANGE_START.isoformat(),
                "exited_at": _RANGE_END.isoformat(),
                "identity_id": None,
                "ph_id": "ph-1",
                "entry_confidence": 0.8,
            }
        ]
    }
    svc = PersonLocationService(
        InMemoryObservationRepository(), InMemorySegmentRepository(), PersonLocationConfig()
    )
    # A live (non-backfill) segment already covers the whole dwell window.
    await svc.ingest_observation(
        person_id="alice",
        observed_at=_RANGE_START,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
        metadata={"room_name": "kitchen"},
    )
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator, location_service=svc)

    ok = await projector.project(_revision())

    assert ok is True
    segments = await svc.room_segments("alice", _RANGE_START, _RANGE_END)
    # Only the pre-existing live segment; the backfill candidate was skipped.
    assert all(s.metadata.get("backfill_revision_id") is None for s in segments)


@pytest.mark.asyncio
async def test_member_autocreated(db_factory):
    _seed_room(db_factory, room_id=1, name="kitchen")
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {
        "dwells": [
            {
                "room_name": "kitchen",
                "entered_at": _RANGE_START.isoformat(),
                "exited_at": _RANGE_END.isoformat(),
                "identity_id": None,
                "ph_id": "ph-1",
                "entry_confidence": 0.8,
            }
        ]
    }
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator)

    await projector.project(_revision(new_identity_id="new-person-99"))

    db = db_factory()
    try:
        member = db.get(HouseholdMember, "new-person-99")
        assert member is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_broadcasts_ws_event_on_success(db_factory):
    _seed_room(db_factory, room_id=1, name="kitchen")
    orchestrator = AsyncMock()
    orchestrator.list_room_dwells.return_value = {
        "dwells": [
            {
                "room_name": "kitchen",
                "entered_at": _RANGE_START.isoformat(),
                "exited_at": _RANGE_END.isoformat(),
                "identity_id": None,
                "ph_id": "ph-1",
                "entry_confidence": 0.8,
            }
        ]
    }
    ws_manager = AsyncMock()
    projector, _svc = _make_projector(db_factory, orchestrator=orchestrator, ws_manager=ws_manager)

    await projector.project(_revision())

    ws_manager.broadcast.assert_called_once()
    payload = ws_manager.broadcast.call_args.args[0]
    assert payload["type"] == "cts_ph_correction"
    assert payload["kind"] == "inferred_backfill"
    assert payload["revision_id"] == "rev-backfill-1"
