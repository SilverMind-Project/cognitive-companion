"""PersonLocationService.room_segments() / observations() / latest_observation() tests.

M32: these three methods are the read API the presence providers, the
activity timeline, and the daily room-time report share (see
`codebase-hardening-m32-cc-location-read-unification.md`, Part A).
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


def _make_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


_START = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
_END = datetime(2026, 6, 2, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_room_segments_returns_sequential_transitions_in_order() -> None:
    """Success path: sequential room transitions come back sorted by entry time."""
    svc = _make_service()
    t0 = _START + timedelta(hours=1)
    t1 = _START + timedelta(hours=3)

    await svc.ingest_observation(
        person_id="alice",
        observed_at=t0,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
        metadata={"room_name": "bedroom"},
    )
    await svc.ingest_observation(
        person_id="alice",
        observed_at=t1,
        source="world_tracker",
        room_id=2,
        confidence=0.9,
        metadata={"room_name": "kitchen"},
    )

    segments = await svc.room_segments("alice", _START, _END)

    assert [s.room_name for s in segments] == ["bedroom", "kitchen"]
    assert segments[0].exited_at == t1  # closed by the kitchen transition
    assert segments[1].exited_at is None  # still open


@pytest.mark.asyncio
async def test_room_segments_open_segment_effective_exited_at_clamped_to_now() -> None:
    """Edge case: an open segment's effective_exited_at clamps to min(now, end),
    not the (possibly future) query window end -- the injectable-clock rule."""
    svc = _make_service()
    entered_at = _START + timedelta(hours=1)
    fake_now = _START + timedelta(hours=5)

    await svc.ingest_observation(
        person_id="alice",
        observed_at=entered_at,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
        metadata={"room_name": "bedroom"},
    )

    segments = await svc.room_segments("alice", _START, _END, now=fake_now)

    assert len(segments) == 1
    assert segments[0].exited_at is None
    assert segments[0].effective_exited_at == fake_now


@pytest.mark.asyncio
async def test_room_segments_excludes_superseded_segment() -> None:
    """Edge case: a segment rewritten by an identity revision is excluded from
    the old identity's query; the replacement appears under the new identity."""
    svc = _make_service()
    entered_at = _START + timedelta(hours=1)
    revision_time = _START + timedelta(hours=2)

    await svc.ingest_observation(
        person_id="unknown_1",
        observed_at=entered_at,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
        metadata={"room_name": "bedroom"},
    )
    await svc.apply_identity_revision(
        old_person_id="unknown_1",
        new_person_id="alice",
        ph_id="ph-1",
        revision_time=revision_time,
    )

    old_segments = await svc.room_segments("unknown_1", _START, _END)
    new_segments = await svc.room_segments("alice", _START, _END)

    assert old_segments == ()
    assert len(new_segments) == 1
    assert new_segments[0].room_name == "bedroom"


@pytest.mark.asyncio
async def test_room_segments_missing_service_data_returns_empty_tuple() -> None:
    """Missing-data path: no observations ever ingested -> empty tuple, not an error."""
    svc = _make_service()

    segments = await svc.room_segments("nobody", _START, _END)

    assert segments == ()


@pytest.mark.asyncio
async def test_observations_filters_by_source() -> None:
    """Success path: sources filter restricts to the given source vocabulary."""
    svc = _make_service()

    await svc.ingest_observation(
        person_id="alice",
        observed_at=_START + timedelta(hours=1),
        source="world_tracker",
        room_id=1,
        confidence=0.9,
    )
    await svc.ingest_observation(
        person_id="alice",
        observed_at=_START + timedelta(hours=2),
        source="recamera_vlm",
        room_id=1,
        confidence=0.7,
    )

    all_obs = await svc.observations("alice", _START, _END)
    filtered = await svc.observations("alice", _START, _END, sources=("recamera_vlm",))

    assert len(all_obs) == 2
    assert len(filtered) == 1
    assert filtered[0].source == "recamera_vlm"


@pytest.mark.asyncio
async def test_latest_observation_returns_most_recent_regardless_of_room_change() -> None:
    """Success path: latest_observation tracks the freshest raw observation,
    unlike where_is()'s open segment which freezes on a same-room repeat."""
    svc = _make_service()
    older = _START + timedelta(hours=1)
    newer = _START + timedelta(hours=2)

    await svc.ingest_observation(
        person_id="alice", observed_at=older, source="world_tracker", room_id=1, confidence=0.9
    )
    await svc.ingest_observation(
        person_id="alice", observed_at=newer, source="world_tracker", room_id=1, confidence=0.9
    )

    latest = await svc.latest_observation("alice")

    assert latest is not None
    assert latest.observed_at == newer


@pytest.mark.asyncio
async def test_latest_observation_missing_data_returns_none() -> None:
    """Missing-data path: no observations ever ingested -> None, not an error."""
    svc = _make_service()

    latest = await svc.latest_observation("nobody")

    assert latest is None
