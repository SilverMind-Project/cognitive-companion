"""M38 Part F: PersonLocationService.ingest_observation() arbitration gate
and .tick() quiet-gap closure, service-level with InMemory repos.

Covers: dense-source refresh keeps a segment alive, sparse-source
quiet-close, cross-source contention (fresh vs. stale), and out-of-order
replay -- the scenarios enumerated in the M38 milestone's Part F.3.
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
from backend.services.person_location.types import FloorPoint

_START = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)


def _make_service(**config_overrides) -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(**config_overrides),
    )


@pytest.mark.asyncio
async def test_dense_source_refresh_keeps_segment_alive_across_ticks():
    """CTS 3Hz-equivalent: repeated same-room observations refresh evidence,
    so tick() never quiet-closes it even well past a sparser source's gap."""
    svc = _make_service(quiet_gap_world_tracker_s=300.0)
    t = _START
    await svc.ingest_observation(
        person_id="alice", observed_at=t, source="world_tracker", room_id=1, confidence=0.9
    )

    for _ in range(5):
        t += timedelta(seconds=100)
        await svc.ingest_observation(
            person_id="alice", observed_at=t, source="world_tracker", room_id=1, confidence=0.9
        )
        await svc.tick(t)

    loc = await svc.where_is("alice")
    assert loc is not None
    assert loc.room_id == 1


@pytest.mark.asyncio
async def test_sparse_source_quiet_closes_and_where_is_goes_none():
    """A single reCamera observation with no follow-up ages out at its gap;
    where_is() returns None afterward (W9)."""
    svc = _make_service(quiet_gap_recamera_vlm_s=2700.0)
    await svc.ingest_observation(
        person_id="bob", observed_at=_START, source="recamera_vlm", room_id=2, confidence=0.7
    )

    assert (await svc.where_is("bob")) is not None

    signals = await svc.tick(_START + timedelta(seconds=2701))

    assert (await svc.where_is("bob")) is None
    # Quiet closure of an observed segment emits no signal (Part C).
    assert signals == []


@pytest.mark.asyncio
async def test_cross_source_contention_dense_live_suppresses_stale_sparse_batch():
    """CTS live (fresh) + a stale reCamera batch reporting a different room:
    the arbiter suppresses the segment effect, but the observation row is
    still recorded (full-fidelity audit)."""
    svc = _make_service()
    await svc.ingest_observation(
        person_id="carol", observed_at=_START, source="world_tracker", room_id=1, confidence=0.9
    )
    # world_tracker keeps refreshing every 10s -- still "live" by the time
    # the stale reCamera batch arrives.
    await svc.ingest_observation(
        person_id="carol",
        observed_at=_START + timedelta(seconds=10),
        source="world_tracker",
        room_id=1,
        confidence=0.9,
    )

    # A reCamera batch claiming room 2, timestamped only 15s after the last
    # world_tracker evidence -- well inside the 30s staleness handoff.
    await svc.ingest_observation(
        person_id="carol",
        observed_at=_START + timedelta(seconds=25),
        source="recamera_vlm",
        room_id=2,
        confidence=0.6,
    )

    loc = await svc.where_is("carol")
    assert loc is not None
    assert loc.room_id == 1  # suppressed: still world_tracker's room

    # The observation row is recorded regardless of arbitration (audit trail).
    recent = await svc.recent_observations(_START, sources=("recamera_vlm",))
    assert any(o.person_id == "carol" and o.room_id == 2 for o in recent)


@pytest.mark.asyncio
async def test_cross_source_contention_allows_takeover_after_cts_goes_quiet():
    """CTS quiet for 35s (past the 30s staleness handoff), then a reCamera
    observation for a different room is allowed through."""
    svc = _make_service()
    await svc.ingest_observation(
        person_id="dave", observed_at=_START, source="world_tracker", room_id=1, confidence=0.9
    )

    await svc.ingest_observation(
        person_id="dave",
        observed_at=_START + timedelta(seconds=35),
        source="recamera_vlm",
        room_id=2,
        confidence=0.6,
    )

    loc = await svc.where_is("dave")
    assert loc is not None
    assert loc.room_id == 2


@pytest.mark.asyncio
async def test_out_of_order_replay_never_rewrites_fresher_segment():
    """A lagged reCamera observation whose observed_at predates the open
    segment's current evidence must never move the segment, even to the
    same room it already reports (out-of-order guard, X13)."""
    svc = _make_service()
    await svc.ingest_observation(
        person_id="erin", observed_at=_START, source="world_tracker", room_id=1, confidence=0.9
    )
    await svc.ingest_observation(
        person_id="erin",
        observed_at=_START + timedelta(seconds=20),
        source="world_tracker",
        room_id=1,
        confidence=0.9,
    )

    # A ~90s-lagged reCamera batch, captured before either world_tracker
    # event but ingested now, claiming a different room.
    await svc.ingest_observation(
        person_id="erin",
        observed_at=_START - timedelta(seconds=5),
        source="recamera_vlm",
        room_id=3,
        confidence=0.6,
    )

    loc = await svc.where_is("erin")
    assert loc is not None
    assert loc.room_id == 1
    assert loc.since == _START  # segment never closed/reopened


@pytest.mark.asyncio
async def test_adapter_never_writes_floor_points():
    """Parity guard (CC-M28 rule, carried into every ingestion path): a
    source with no real coordinates must produce floor_point=None, never a
    fabricated (0, 0)."""
    svc = _make_service()
    await svc.ingest_observation(
        person_id="frank",
        observed_at=_START,
        source="recamera_vlm",
        room_id=1,
        confidence=0.7,
        floor_point=None,
    )
    assert await svc.latest_floor_point("frank") is None


@pytest.mark.asyncio
async def test_legitimate_floor_point_still_ingested():
    svc = _make_service()
    await svc.ingest_observation(
        person_id="grace",
        observed_at=_START,
        source="world_tracker",
        room_id=1,
        confidence=0.9,
        floor_point=FloorPoint(x_m=1.0, y_m=2.0),
    )
    # max_age_s is relative to real wall-clock time, not the fixed _START
    # fixture time, so it must be large enough to cover the gap.
    fp = await svc.latest_floor_point("grace", max_age_s=10**9)
    assert fp is not None
    assert fp.x_m == 1.0
    assert fp.y_m == 2.0
