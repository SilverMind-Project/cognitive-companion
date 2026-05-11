"""Tests for the StreamConsumer base class."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.cts.stream_consumer import ConsumerConfig, StreamConsumer


class _Consumer(StreamConsumer[str]):
    """Test consumer: decode returns the raw payload as a string, handle records calls."""

    STREAM = "test.stream"
    GROUP = "test-group"

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        super().__init__(
            ConsumerConfig(
                redis_url=redis_url,
                stream=self.STREAM,
                group=self.GROUP,
                consumer_id="test-consumer",
                block_ms=100,
                batch_size=4,
            )
        )
        self.handled: list[str] = []
        self.decode_fail_on: set[bytes] = set()  # message_ids to simulate decode failure on

    def decode(self, message_id: bytes, fields: dict) -> str | None:
        if message_id in self.decode_fail_on:
            return None
        payload = fields.get(b"data", b"")
        if isinstance(payload, bytes):
            return payload.decode()
        return str(payload)

    async def handle(self, msg: str) -> bool:
        self.handled.append(msg)
        return True


class TestStreamConsumerDecode:
    """Unit tests for the decode/handle contract (no Redis)."""

    def test_decode_success(self) -> None:
        consumer = _Consumer()
        result = consumer.decode(b"msg-1", {b"data": b"hello"})
        assert result == "hello"

    def test_decode_failure_returns_none(self) -> None:
        consumer = _Consumer()
        consumer.decode_fail_on.add(b"msg-1")
        result = consumer.decode(b"msg-1", {b"data": b"hello"})
        assert result is None


class TestStreamConsumerPendingDrain:
    """Tests for the pending-task drain on stop."""

    @pytest.mark.asyncio
    async def test_stop_drains_pending_tasks(self) -> None:
        """Tasks created by _fan_out should complete before stop() returns."""
        consumer = _Consumer()

        # Block tasks until we're ready to observe them.
        gate: asyncio.Event = asyncio.Event()

        async def blocked_handle(msg: str) -> bool:
            await gate.wait()
            consumer.handled.append(msg)
            return True

        consumer.handle = blocked_handle

        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock()
        mock_redis.xgroup_create = AsyncMock()
        mock_redis.xautoclaim = AsyncMock(return_value=None)
        mock_redis.close = AsyncMock()
        consumer._redis = mock_redis

        messages = [
            (b"msg-1", {b"data": b"alpha"}),
            (b"msg-2", {b"data": b"beta"}),
        ]

        # Fan out — creates 2 tasks that are blocked on gate.
        await consumer._fan_out(messages)

        # Tasks should be tracked in _pending.
        assert len(consumer._pending) == 2

        # Release tasks, then stop (which drains them).
        gate.set()
        await consumer.stop()
        assert len(consumer._pending) == 0
        assert set(consumer.handled) == {"alpha", "beta"}

    @pytest.mark.asyncio
    async def test_pending_tasks_cleaned_up_on_exception(self) -> None:
        """A task that raises should still be removed from pending."""
        consumer = _Consumer()

        async def failing_handle(msg: str) -> bool:
            raise RuntimeError("boom")

        consumer.handle = failing_handle

        mock_redis = MagicMock()
        mock_redis.xack = AsyncMock()
        mock_redis.close = AsyncMock()
        consumer._redis = mock_redis

        # Manually create and track a task.
        task = asyncio.create_task(consumer._run_one(b"msg-1", "test"))
        consumer._pending.add(task)
        task.add_done_callback(consumer._pending.discard)

        # Let the task run to completion (it will fail silently inside _run_one).
        await asyncio.sleep(0.05)
        # _run_one catches the exception and returns, so the task completes.
        # The done callback removes it from pending.
        assert len(consumer._pending) == 0
