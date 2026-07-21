"""SegmentRepository backfill-batch parity: InMemory vs SqlAlchemy (M05).

The idempotency invariant ("a redelivered projector run inserts nothing new")
is enforced by the partial unique index on (backfill_revision_id,
entered_at), not by the read-then-write check alone. These tests prove both
repository peers report the same true-inserted count under a conflicting
re-insert, matching the parity-matrix rule in the engineering-standards
skill for any new filtered/enforced repo behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.services.person_location.repositories import (
    InMemorySegmentRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.types import PresenceSegment

_ENTERED = datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
_EXITED = datetime(2026, 7, 20, 7, 0, tzinfo=UTC)


def _segment(*, revision_id: str = "rev-1", entered_at: datetime = _ENTERED) -> PresenceSegment:
    return PresenceSegment(
        id=uuid4(),
        person_id="alice",
        room_id=1,
        entered_at=entered_at,
        exited_at=_EXITED,
        entry_source="observed",
        exit_source="observed",
        confidence=0.8,
        backfill_revision_id=revision_id,
        metadata={"backfill_revision_id": revision_id},
    )


@pytest.mark.asyncio
async def test_inmemory_insert_backfill_batch_skips_conflicting_key() -> None:
    repo = InMemorySegmentRepository()
    seg_a = _segment()

    first = await repo.insert_backfill_batch([seg_a])
    # Same (revision_id, entered_at) key, different segment id: a redelivery
    # retry with a freshly-generated candidate id must still be recognized
    # as a duplicate by the (backfill_revision_id, entered_at) pair.
    seg_b = _segment()
    second = await repo.insert_backfill_batch([seg_b])

    assert first == 1
    assert second == 0
    assert await repo.exists_for_backfill_revision("rev-1") is True


@pytest.mark.asyncio
async def test_sqlalchemy_insert_backfill_batch_skips_conflicting_key(db_factory) -> None:
    db = db_factory()
    try:
        db.add(Room(id=1, name="kitchen"))
        db.add(HouseholdMember(id="alice", name="Alice"))
        db.commit()
    finally:
        db.close()

    repo = SqlAlchemySegmentRepository(db_factory)
    seg_a = _segment()
    seg_b = _segment()  # different id, same (revision_id, entered_at)

    first = await repo.insert_backfill_batch([seg_a])
    second = await repo.insert_backfill_batch([seg_b])

    assert first == 1
    assert second == 0
    assert await repo.exists_for_backfill_revision("rev-1") is True
    assert await repo.exists_for_backfill_revision("rev-does-not-exist") is False


@pytest.mark.asyncio
async def test_sqlalchemy_insert_backfill_batch_atomic_across_rows(db_factory) -> None:
    """One conflicting row in a multi-row batch does not block the others."""
    db = db_factory()
    try:
        db.add(Room(id=1, name="kitchen"))
        db.add(HouseholdMember(id="alice", name="Alice"))
        db.commit()
    finally:
        db.close()

    repo = SqlAlchemySegmentRepository(db_factory)
    existing = _segment(revision_id="rev-2", entered_at=_ENTERED)
    await repo.insert_backfill_batch([existing])

    batch = [
        _segment(revision_id="rev-2", entered_at=_ENTERED),  # conflicts
        _segment(revision_id="rev-2", entered_at=datetime(2026, 7, 20, 8, 0, tzinfo=UTC)),  # new
    ]
    inserted = await repo.insert_backfill_batch(batch)

    assert inserted == 1


@pytest.mark.asyncio
async def test_sqlalchemy_insert_backfill_batch_empty_list_is_noop(db_factory) -> None:
    repo = SqlAlchemySegmentRepository(db_factory)
    assert await repo.insert_backfill_batch([]) == 0
