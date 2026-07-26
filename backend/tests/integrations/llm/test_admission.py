"""Tests for :mod:`backend.integrations.llm.admission` (DL-M09 Part A)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.integrations.llm.admission import (
    LLMAdmissionController,
    LLMAdmissionTimeout,
)


class _FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.mark.asyncio
async def test_vision_lane_serializes() -> None:
    """A second vision admit only starts after the first releases."""
    controller = LLMAdmissionController(
        max_concurrent_vision=1, max_concurrent_text=2, queue_timeout_s=5.0
    )
    order: list[str] = []
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def first() -> None:
        async with controller.admit("vision", "caller-a"):
            order.append("first_start")
            await release_first.wait()
            order.append("first_end")

    async def second() -> None:
        async with controller.admit("vision", "caller-b"):
            order.append("second_start")
            second_started.set()

    task1 = asyncio.create_task(first())
    await asyncio.sleep(0)  # let first() acquire before second() is scheduled
    task2 = asyncio.create_task(second())
    await asyncio.sleep(0)

    assert order == ["first_start"]
    assert not second_started.is_set()

    release_first.set()
    await asyncio.gather(task1, task2)

    assert order == ["first_start", "first_end", "second_start"]


@pytest.mark.asyncio
async def test_text_lane_allows_two() -> None:
    """Two concurrent text admits both start without waiting on each other."""
    controller = LLMAdmissionController(
        max_concurrent_vision=1, max_concurrent_text=2, queue_timeout_s=5.0
    )
    started: list[str] = []
    release = asyncio.Event()

    async def worker(name: str) -> None:
        async with controller.admit("text", name):
            started.append(name)
            await release.wait()

    task1 = asyncio.create_task(worker("a"))
    task2 = asyncio.create_task(worker("b"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert set(started) == {"a", "b"}

    release.set()
    await asyncio.gather(task1, task2)


@pytest.mark.asyncio
async def test_queue_timeout_raises_typed_error() -> None:
    """A queued admit that cannot start within queue_timeout_s fails closed."""
    controller = LLMAdmissionController(
        max_concurrent_vision=1, max_concurrent_text=2, queue_timeout_s=0.05
    )
    holder_started = asyncio.Event()
    keep_holding = asyncio.Event()

    async def holder() -> None:
        async with controller.admit("vision", "holder"):
            holder_started.set()
            await keep_holding.wait()

    task = asyncio.create_task(holder())
    await holder_started.wait()

    assert controller.queue_depth("vision") == 0
    with pytest.raises(LLMAdmissionTimeout) as excinfo:
        async with controller.admit("vision", "impatient"):
            pass  # pragma: no cover - never reached

    assert excinfo.value.lane == "vision"
    assert excinfo.value.caller == "impatient"
    assert controller.queue_depth("vision") == 0

    keep_holding.set()
    await task

    records = controller.snapshot()
    timeout_records = [r for r in records if r.outcome == "timeout"]
    assert len(timeout_records) == 1
    assert timeout_records[0].caller == "impatient"


@pytest.mark.asyncio
async def test_metrics_recorded_by_caller_lane_outcome() -> None:
    """Ring buffer and counters record caller/lane/outcome for ok and error calls."""
    controller = LLMAdmissionController(max_concurrent_vision=1, max_concurrent_text=2)

    async with controller.admit("vision", "rule:tea_intent", model_id="cosmos_reason2"):
        pass

    with pytest.raises(RuntimeError):
        async with controller.admit("vision", "rule:tea_intent", model_id="cosmos_reason2"):
            raise RuntimeError("boom")

    counters = controller.counters()
    assert counters[("rule:tea_intent", "vision", "ok")] == 1
    assert counters[("rule:tea_intent", "vision", "error")] == 1

    records = controller.snapshot()
    assert len(records) == 2
    assert {r.outcome for r in records} == {"ok", "error"}
    assert all(r.model_id == "cosmos_reason2" for r in records)


@pytest.mark.asyncio
async def test_injected_clock_used_for_timestamps_and_durations() -> None:
    """Queue-wait/execution durations and record timestamps use the injected clock."""
    clock = _FakeClock()
    controller = LLMAdmissionController(
        max_concurrent_vision=1, max_concurrent_text=2, time_fn=clock
    )

    async with controller.admit("text", "caller"):
        clock.advance(seconds=2)

    record = controller.snapshot()[0]
    assert record.execution_ms == 2000
    assert record.at == clock.now


@pytest.mark.asyncio
async def test_ring_buffer_capacity_bounded() -> None:
    controller = LLMAdmissionController(max_concurrent_text=2, ring_buffer_size=2)
    for i in range(3):
        async with controller.admit("text", f"caller-{i}"):
            pass

    assert controller.ring_buffer_capacity == 2
    assert len(controller.snapshot()) == 2
    # Oldest record (caller-0) was evicted.
    assert [r.caller for r in controller.snapshot()] == ["caller-1", "caller-2"]
