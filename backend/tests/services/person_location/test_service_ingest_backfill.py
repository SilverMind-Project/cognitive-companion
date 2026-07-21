"""PersonLocationService.ingest_backfill_segments tests (identity-continuity M05).

Room resolution and dwell-fetching are the projector's job (see
test_backfill_projector.py); these tests exercise the service's own
contract: clamping to the revision range, dropping unmapped rooms and
zero-length dwells, the >50% overlap guard against live segments, and
idempotency under the same revision_id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.services.person_location.config import PersonLocationConfig
from backend.services.person_location.repositories import (
    InMemoryObservationRepository,
    InMemorySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import BackfillDwellInput

_START = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
_END = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


def _make_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(), InMemorySegmentRepository(), PersonLocationConfig()
    )


@pytest.mark.asyncio
async def test_inserts_one_segment_per_dwell() -> None:
    svc = _make_service()
    dwells = [
        BackfillDwellInput(
            room_id=1,
            room_name="kitchen",
            entered_at=_START,
            exited_at=_START + timedelta(hours=1),
            confidence=0.8,
        ),
        BackfillDwellInput(
            room_id=2,
            room_name="bedroom",
            entered_at=_START + timedelta(hours=1),
            exited_at=_END,
            confidence=0.7,
        ),
    ]

    result = await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    assert result.inserted == 2
    segments = await svc.room_segments("alice", _START, _END)
    assert [s.room_name for s in segments] == ["kitchen", "bedroom"]
    assert all(s.exited_at is not None for s in segments)  # all closed


@pytest.mark.asyncio
async def test_clamps_dwell_to_revision_range() -> None:
    svc = _make_service()
    dwells = [
        BackfillDwellInput(
            room_id=1,
            room_name="kitchen",
            entered_at=_START - timedelta(hours=2),  # before range_start
            exited_at=_END + timedelta(hours=2),  # after range_end
            confidence=0.8,
        )
    ]

    await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    segments = await svc.room_segments(
        "alice", _START - timedelta(hours=3), _END + timedelta(hours=3)
    )
    assert len(segments) == 1
    assert segments[0].entered_at == _START
    assert segments[0].exited_at == _END


@pytest.mark.asyncio
async def test_dwell_with_unmapped_room_is_dropped() -> None:
    svc = _make_service()
    dwells = [
        BackfillDwellInput(
            room_id=None,
            room_name="unmapped-room",
            entered_at=_START,
            exited_at=_END,
            confidence=0.8,
        )
    ]

    result = await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    assert result.inserted == 0
    assert result.dropped_unmapped_room == 1


@pytest.mark.asyncio
async def test_zero_length_dwell_after_clamping_is_dropped() -> None:
    svc = _make_service()
    dwells = [
        BackfillDwellInput(
            room_id=1,
            room_name="kitchen",
            entered_at=_END + timedelta(hours=1),  # entirely after range_end
            exited_at=_END + timedelta(hours=2),
            confidence=0.8,
        )
    ]

    result = await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    assert result.inserted == 0
    assert result.dropped_zero_length == 1


@pytest.mark.asyncio
async def test_dwell_majority_overlapping_live_segment_is_skipped() -> None:
    svc = _make_service()
    # A live (non-backfill) segment covering the whole window already exists.
    await svc.ingest_observation(
        person_id="alice",
        observed_at=_START,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
        metadata={"room_name": "kitchen"},
    )
    dwells = [
        BackfillDwellInput(
            room_id=1, room_name="kitchen", entered_at=_START, exited_at=_END, confidence=0.5
        )
    ]

    result = await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    assert result.inserted == 0
    assert result.overlap_skipped == 1


@pytest.mark.asyncio
async def test_second_call_with_same_revision_id_is_a_noop() -> None:
    svc = _make_service()
    dwells = [
        BackfillDwellInput(
            room_id=1, room_name="kitchen", entered_at=_START, exited_at=_END, confidence=0.8
        )
    ]

    first = await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )
    second = await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    assert first.inserted == 1
    assert second.inserted == 0
    assert second.skipped_duplicate == 1
    segments = await svc.room_segments("alice", _START, _END)
    assert len(segments) == 1


@pytest.mark.asyncio
async def test_apply_identity_revision_supersedes_backfilled_segments() -> None:
    """A later operator correction reaches a backfilled segment through the
    SSOT's own supersession machinery (``apply_identity_revision``), the
    same path a live segment goes through -- no backfill-specific
    supersession code exists or is needed.
    """
    seg_repo = InMemorySegmentRepository()
    svc = PersonLocationService(InMemoryObservationRepository(), seg_repo, PersonLocationConfig())
    dwells = [
        BackfillDwellInput(
            room_id=1, room_name="kitchen", entered_at=_START, exited_at=_END, confidence=0.8
        )
    ]
    await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )
    [backfilled] = await svc.room_segments("alice", _START, _END)

    # An operator later corrects the backfilled attribution: it was bob, not
    # alice. revision_time sits at the segment's exited_at so the default
    # revision_horizon_s window around it overlaps the (closed) segment.
    await svc.apply_identity_revision(
        old_person_id="alice",
        new_person_id="bob",
        ph_id="ph-1",
        revision_time=_END,
    )

    alice_segments = await svc.room_segments("alice", _START, _END)
    assert alice_segments == ()  # superseded, excluded from the read model

    bob_segments = await svc.room_segments("bob", _START, _END)
    assert len(bob_segments) == 1
    assert bob_segments[0].room_name == "kitchen"

    original_row = await seg_repo.get_by_id(backfilled.id)
    assert original_row is not None
    assert original_row.superseded_by is not None


@pytest.mark.asyncio
async def test_has_backfill_segments_reflects_insertion() -> None:
    svc = _make_service()
    assert await svc.has_backfill_segments("rev-1") is False

    dwells = [
        BackfillDwellInput(
            room_id=1, room_name="kitchen", entered_at=_START, exited_at=_END, confidence=0.8
        )
    ]
    await svc.ingest_backfill_segments(
        revision_id="rev-1", person_id="alice", dwells=dwells, range_start=_START, range_end=_END
    )

    assert await svc.has_backfill_segments("rev-1") is True
