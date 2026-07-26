"""PersonLocationService.dwell_episodes() tests (DL-M08 Part B).

Built on room_segments() so it inherits open-segment clamping and identity-
revision supersession for free; these tests focus on the gap-merge and
episode-boundary behavior dwell_episodes adds on top.
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

_BATHROOM = 7
_HALLWAY = 8

_START = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
_END = datetime(2026, 6, 2, 0, 0, tzinfo=UTC)


def _make_service() -> PersonLocationService:
    return PersonLocationService(
        InMemoryObservationRepository(),
        InMemorySegmentRepository(),
        PersonLocationConfig(),
    )


@pytest.mark.asyncio
async def test_dwell_episodes_empty_history_returns_empty_tuple() -> None:
    svc = _make_service()

    episodes = await svc.dwell_episodes("alice", _BATHROOM, _START, _END)

    assert episodes == ()


@pytest.mark.asyncio
async def test_dwell_episodes_merges_across_a_short_gap() -> None:
    """Two bathroom stays separated by a 90s dropout merge into one episode."""
    svc = _make_service()
    enter1 = _START + timedelta(hours=1)
    exit1 = enter1 + timedelta(minutes=5)
    enter2 = exit1 + timedelta(seconds=90)
    exit2 = enter2 + timedelta(minutes=4)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter1)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit1)
    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter2)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit2)

    episodes = await svc.dwell_episodes(
        "alice", _BATHROOM, _START, _END, merge_gap_s=120
    )

    assert len(episodes) == 1
    assert episodes[0].entered_at == enter1
    assert episodes[0].exited_at == exit2
    assert episodes[0].minutes == pytest.approx(10.5, abs=0.01)


@pytest.mark.asyncio
async def test_dwell_episodes_does_not_merge_across_a_long_gap() -> None:
    """Two bathroom stays separated by more than merge_gap_s stay separate episodes."""
    svc = _make_service()
    enter1 = _START + timedelta(hours=1)
    exit1 = enter1 + timedelta(minutes=5)
    enter2 = exit1 + timedelta(minutes=10)
    exit2 = enter2 + timedelta(minutes=3)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter1)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit1)
    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter2)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit2)

    episodes = await svc.dwell_episodes(
        "alice", _BATHROOM, _START, _END, merge_gap_s=120
    )

    assert len(episodes) == 2
    assert episodes[0].minutes == pytest.approx(5.0, abs=0.01)
    assert episodes[1].minutes == pytest.approx(3.0, abs=0.01)


@pytest.mark.asyncio
async def test_dwell_episodes_inferred_only_bathroom_episode_counts() -> None:
    """The no-camera case: an inferred_transit-only segment still produces an episode."""
    svc = _make_service()
    enter = _START + timedelta(hours=2)
    exit_ = enter + timedelta(minutes=8)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit_)

    segments = await svc.room_segments("alice", _START, _END)
    assert all(s.entry_source == "inferred_transit" for s in segments if s.room_id == _BATHROOM)

    episodes = await svc.dwell_episodes("alice", _BATHROOM, _START, _END)

    assert len(episodes) == 1
    assert episodes[0].minutes == pytest.approx(8.0, abs=0.01)


@pytest.mark.asyncio
async def test_dwell_episodes_open_segment_clamped_by_fake_now() -> None:
    """An open (still-in-progress) bathroom segment clamps to the injected now."""
    svc = _make_service()
    enter = _START + timedelta(hours=1)
    fake_now = enter + timedelta(minutes=6)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter)

    episodes = await svc.dwell_episodes("alice", _BATHROOM, _START, _END, now=fake_now)

    assert len(episodes) == 1
    assert episodes[0].exited_at == fake_now
    assert episodes[0].minutes == pytest.approx(6.0, abs=0.01)


@pytest.mark.asyncio
async def test_dwell_episodes_crosses_window_boundary_keeps_true_start() -> None:
    """A segment that started before the query window keeps its real entered_at."""
    svc = _make_service()
    window_start = _START + timedelta(hours=5)
    true_enter = _START + timedelta(hours=4, minutes=50)  # 10 min before window_start
    exit_ = window_start + timedelta(minutes=3)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, true_enter)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit_)

    episodes = await svc.dwell_episodes("alice", _BATHROOM, window_start, _END)

    assert len(episodes) == 1
    assert episodes[0].entered_at == true_enter
    assert episodes[0].minutes == pytest.approx(13.0, abs=0.01)


@pytest.mark.asyncio
async def test_dwell_episodes_short_episode_is_not_pre_filtered() -> None:
    """dwell_episodes returns every episode; min-duration filtering is the caller's job."""
    svc = _make_service()
    enter = _START + timedelta(hours=1)
    exit_ = enter + timedelta(minutes=1)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit_)

    episodes = await svc.dwell_episodes("alice", _BATHROOM, _START, _END)

    assert len(episodes) == 1
    assert episodes[0].minutes == pytest.approx(1.0, abs=0.01)


@pytest.mark.asyncio
async def test_dwell_episodes_filters_to_requested_room_only() -> None:
    """A different room's segment does not contribute to the requested room's episodes."""
    svc = _make_service()
    enter = _START + timedelta(hours=1)
    exit_ = enter + timedelta(minutes=5)

    await svc.ingest_room_transition("alice", "tz1", "enter", _BATHROOM, _HALLWAY, enter)
    await svc.ingest_room_transition("alice", "tz1", "exit", _BATHROOM, _HALLWAY, exit_)

    episodes = await svc.dwell_episodes("alice", _HALLWAY, _START, _END)

    # The exit transition opens a hallway segment too; it should appear here,
    # not double-count under the bathroom room_id.
    bathroom_episodes = await svc.dwell_episodes("alice", _BATHROOM, _START, _END)
    assert len(bathroom_episodes) == 1
    assert all(e.entered_at != enter for e in episodes)
