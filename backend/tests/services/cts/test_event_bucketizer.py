"""Characterization tests for the CTS event bucketizer."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from backend.services.cts.event_bucketizer import CtsEventBucketizer, CtsWindowTrigger


def _event(
    *,
    camera_id: str = "cam-1",
    identities: tuple[str, ...] = (),
) -> dict:
    return {
        "camera_id": camera_id,
        "event_time": datetime.now(UTC).isoformat(),
        "room_name": "kitchen",
        "detections": [{"identity_id": identity_id} for identity_id in identities],
        "detection_count": len(identities),
        "minio_key": f"frames/{camera_id}/sample.jpg",
    }


def _trigger(**overrides) -> CtsWindowTrigger:
    values = {
        "id": "trigger-1",
        "name": "Kitchen activity",
        "window_seconds": 60.0,
        "min_detections": 1,
        "min_identities": 0,
        "cameras": ["cam-1"],
        "cooldown_seconds": 0.0,
    }
    values.update(overrides)
    return CtsWindowTrigger(**values)


async def _drain_fire_task() -> None:
    await asyncio.sleep(0)


def test_ingest_appends_event_to_camera_buffer() -> None:
    bucketizer = CtsEventBucketizer()
    event = _event()

    bucketizer.ingest(event)

    assert bucketizer.forward_buffer("window-1", "cam-1", 0.0) == [event]


def test_buffer_stats_reports_per_camera_sizes() -> None:
    bucketizer = CtsEventBucketizer()

    bucketizer.ingest(_event(camera_id="cam-1"))
    bucketizer.ingest(_event(camera_id="cam-1"))
    bucketizer.ingest(_event(camera_id="cam-2"))

    assert bucketizer.buffer_stats() == {"cam-1": 2, "cam-2": 1}


async def test_trigger_fires_when_min_detections_met() -> None:
    pipeline = AsyncMock()
    trigger = _trigger(min_detections=2)
    bucketizer = CtsEventBucketizer(
        pipeline=pipeline,
        get_triggers=lambda: [trigger],
    )

    bucketizer.ingest(_event())
    bucketizer.ingest(_event())
    await _drain_fire_task()

    pipeline.fire_event.assert_awaited_once()
    call = pipeline.fire_event.await_args
    assert call.kwargs["source"] == "cts"
    assert call.kwargs["kind"] == "cts_window"
    assert len(call.kwargs["payload"]["frames"]) == 2


async def test_trigger_does_not_fire_below_min_detections() -> None:
    pipeline = AsyncMock()
    trigger = _trigger(min_detections=2)
    bucketizer = CtsEventBucketizer(
        pipeline=pipeline,
        get_triggers=lambda: [trigger],
    )

    bucketizer.ingest(_event())
    await _drain_fire_task()

    pipeline.fire_event.assert_not_awaited()


async def test_trigger_respects_min_identities() -> None:
    pipeline = AsyncMock()
    trigger = _trigger(min_identities=2)
    bucketizer = CtsEventBucketizer(
        pipeline=pipeline,
        get_triggers=lambda: [trigger],
    )

    bucketizer.ingest(_event(identities=("resident-1",)))
    await _drain_fire_task()
    pipeline.fire_event.assert_not_awaited()

    bucketizer.ingest(_event(identities=("resident-2",)))
    await _drain_fire_task()

    pipeline.fire_event.assert_awaited_once()


async def test_trigger_respects_cooldown() -> None:
    now = [100.0]
    pipeline = AsyncMock()
    trigger = _trigger(cooldown_seconds=30.0)
    bucketizer = CtsEventBucketizer(
        pipeline=pipeline,
        get_triggers=lambda: [trigger],
        time_fn=lambda: now[0],
    )

    bucketizer.ingest(_event())
    bucketizer.ingest(_event())
    await _drain_fire_task()

    pipeline.fire_event.assert_awaited_once()

    now[0] = 130.0
    bucketizer.ingest(_event())
    await _drain_fire_task()

    assert pipeline.fire_event.await_count == 2


def test_forward_buffer_returns_camera_events() -> None:
    bucketizer = CtsEventBucketizer()
    first = _event()
    second = _event()

    bucketizer.ingest(first)
    bucketizer.ingest(second)

    assert bucketizer.forward_buffer("window-1", "cam-1", 5.0) == [first, second]


def test_buffer_state_reports_depth_capacity_and_origin_cts() -> None:
    bucketizer = CtsEventBucketizer()
    event = _event()
    bucketizer.ingest(event)

    states = bucketizer.buffer_state()

    assert len(states) == 1
    assert states[0].camera_id == "cam-1"
    assert states[0].origin == "cts"
    assert states[0].buffer_depth == 1
    assert states[0].buffer_capacity == 512
    assert states[0].last_event_at == event["event_time"]
