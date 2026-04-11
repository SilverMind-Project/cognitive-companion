"""Tests for EventAggregator  buffering, flushing, cooldown, and data integrity."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.event_aggregator import EventAggregator


def _make_aggregator(db_factory, callback=None, **config_overrides):
    """Build an EventAggregator with a mock MinIO client."""
    minio = MagicMock()
    minio.extract_object_name.side_effect = lambda p: p.split("/")[-1]
    minio.generate_presigned_url.side_effect = lambda n: f"https://minio/{n}"

    config = {
        "batch_size": 3,
        "window_seconds": 60.0,
        "cooldown_seconds": 300.0,
        "media_retention_minutes": 30,
        **config_overrides,
    }

    if callback is None:
        callback = AsyncMock()

    agg = EventAggregator(
        config=config,
        db_session_factory=db_factory,
        minio_client=minio,
        process_callback=callback,
    )
    return agg, minio, callback


class TestEventAggregatorBuffering:
    async def test_events_accumulate_in_buffer(self, db_factory):
        agg, _, _ = _make_aggregator(db_factory)
        await agg.add_event("cam1", "minio://bucket/img1.jpg")
        await agg.add_event("cam1", "minio://bucket/img2.jpg")

        assert len(agg.buffers.get("cam1", [])) == 2

    async def test_batch_flush_on_size(self, db_factory):
        callback = AsyncMock()
        agg, _, _ = _make_aggregator(db_factory, callback=callback, batch_size=2)

        await agg.add_event("cam1", "minio://bucket/img1.jpg")
        await agg.add_event("cam1", "minio://bucket/img2.jpg")  # triggers flush

        callback.assert_awaited_once()
        # Buffer should be cleared after successful flush
        assert agg.buffers.get("cam1", []) == []

    async def test_cooldown_drops_events(self, db_factory):
        callback = AsyncMock()
        agg, _, _ = _make_aggregator(
            db_factory, callback=callback, batch_size=2, cooldown_seconds=3600
        )

        # First two events trigger flush and set cooldown
        await agg.add_event("cam1", "minio://bucket/img1.jpg")
        await agg.add_event("cam1", "minio://bucket/img2.jpg")
        assert callback.await_count == 1

        # Subsequent events should be dropped while cooldown is active
        await agg.add_event("cam1", "minio://bucket/img3.jpg")
        await agg.add_event("cam1", "minio://bucket/img4.jpg")
        assert callback.await_count == 1  # still only called once

    async def test_multiple_sensors_independent(self, db_factory):
        agg, _, _ = _make_aggregator(db_factory, batch_size=5)
        await agg.add_event("cam1", "minio://bucket/a.jpg")
        await agg.add_event("cam2", "minio://bucket/b.jpg")

        assert len(agg.buffers.get("cam1", [])) == 1
        assert len(agg.buffers.get("cam2", [])) == 1

    async def test_timer_started_on_first_event(self, db_factory):
        agg, _, _ = _make_aggregator(db_factory, batch_size=10)
        await agg.add_event("cam1", "minio://bucket/img1.jpg")

        assert "cam1" in agg.timers
        assert not agg.timers["cam1"].done()
        # Clean up
        agg.timers["cam1"].cancel()

    async def test_timer_cancelled_on_batch_flush(self, db_factory):
        agg, _, _ = _make_aggregator(db_factory, batch_size=2)
        await agg.add_event("cam1", "minio://bucket/img1.jpg")
        timer = agg.timers.get("cam1")
        assert timer is not None

        await agg.add_event("cam1", "minio://bucket/img2.jpg")  # triggers flush
        # Timer should be gone after flush
        assert agg.timers.get("cam1") is None


class TestEventAggregatorDataIntegrity:
    async def test_buffer_restored_on_db_failure(self, db_factory):
        """If the DB write fails the buffer must not be permanently discarded."""
        callback = AsyncMock()
        agg, _minio, _ = _make_aggregator(db_factory, callback=callback, batch_size=2)

        # Add events to buffer
        agg.buffers["cam1"] = ["minio://bucket/img1.jpg", "minio://bucket/img2.jpg"]

        # Make the DB write fail
        bad_db = MagicMock()
        bad_db.merge.side_effect = Exception("DB unavailable")
        bad_db.rollback = MagicMock()
        bad_db.close = MagicMock()
        agg._db_session_factory = MagicMock(return_value=bad_db)

        with pytest.raises(Exception, match="DB unavailable"):
            await agg.flush("cam1")

        # Buffer must still be present so the data isn't lost
        assert "cam1" in agg.buffers
        assert len(agg.buffers["cam1"]) == 2

    async def test_flush_empty_buffer_is_noop(self, db_factory):
        callback = AsyncMock()
        agg, _, _ = _make_aggregator(db_factory, callback=callback)

        await agg.flush("nonexistent_sensor")

        callback.assert_not_awaited()

    async def test_callback_called_with_correct_paths(self, db_factory):
        callback = AsyncMock()
        agg, _, _ = _make_aggregator(db_factory, callback=callback, batch_size=2)

        paths = ["minio://bucket/img1.jpg", "minio://bucket/img2.jpg"]
        await agg.add_event("cam1", paths[0])
        await agg.add_event("cam1", paths[1])

        callback.assert_awaited_once_with("cam1", paths)

    async def test_cooldown_set_after_successful_flush(self, db_factory):
        agg, _, _ = _make_aggregator(db_factory, batch_size=1, cooldown_seconds=100)

        import time

        before = time.monotonic()
        await agg.add_event("cam1", "minio://bucket/img1.jpg")

        assert "cam1" in agg.cooldowns
        assert agg.cooldowns["cam1"] > before + 99  # at least 99s in the future


class TestEventAggregatorWindowTimer:
    async def test_window_timer_flushes_partial_batch(self, db_factory):
        """A partial buffer (< batch_size) should flush when the window expires."""
        callback = AsyncMock()
        agg, _, _ = _make_aggregator(
            db_factory, callback=callback, batch_size=10, window_seconds=0.05
        )

        await agg.add_event("cam1", "minio://bucket/img1.jpg")
        assert callback.await_count == 0  # batch not full yet

        # Wait for timer to expire
        await asyncio.sleep(0.15)
        assert callback.await_count == 1
