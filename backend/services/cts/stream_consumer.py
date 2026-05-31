"""Shared Redis Streams consumer-group base class.

Reused by all four CTS subscribers (tracking events, identity revisions,
dementia signals, scene samples) so each subscriber focuses on decode
and handle logic.

Handles: consumer-group creation, pending-entry reclamation via
XAUTOCLAIM, parse-or-skip for malformed messages, backpressure via
bounded asyncio semaphore, graceful shutdown, and structured error
logging.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

import redis.asyncio as aioredis

from backend.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
type StreamFields = dict[bytes | str, bytes | str]
type StreamMessage = tuple[bytes, StreamFields]


@dataclass
class ConsumerConfig:
    redis_url: str
    stream: str
    group: str
    consumer_id: str
    block_ms: int = 5000
    batch_size: int = 16
    concurrency: int = 4
    reclaim_idle_ms: int = 60_000


class StreamConsumer[T](ABC):
    """Base class for a Redis Streams consumer-group reader.

    Override ``decode()`` to parse raw Redis fields into your message
    type ``T`` (return ``None`` to drop+ack).  Override ``handle()``
    to act on the message.  Return ``True`` to ack, ``False`` to
    leave it pending for retry.
    """

    def __init__(self, cfg: ConsumerConfig) -> None:
        self._cfg = cfg
        self._redis: aioredis.Redis | None = None
        self._sem = asyncio.Semaphore(cfg.concurrency)
        self._stopped = asyncio.Event()
        self._pending: set[asyncio.Task[object]] = set()

    @abstractmethod
    def decode(self, message_id: bytes, fields: StreamFields) -> T | None: ...

    @abstractmethod
    async def handle(self, msg: T) -> bool: ...

    async def start(self) -> None:
        read_timeout_s = max((self._cfg.block_ms / 1000.0) + 5.0, 10.0)
        self._redis = aioredis.from_url(
            self._cfg.redis_url,
            decode_responses=False,
            socket_timeout=read_timeout_s,
            socket_connect_timeout=5.0,
            health_check_interval=30,
        )
        await self._ensure_group()
        logger.info(
            "cts_stream_consumer_started",
            stream=self._cfg.stream,
            group=self._cfg.group,
            consumer=self._cfg.consumer_id,
        )
        try:
            while not self._stopped.is_set():
                await self._tick()
        finally:
            await self._redis.close()

    async def stop(self) -> None:
        self._stopped.set()
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
            self._pending.clear()

    async def _tick(self) -> None:
        assert self._redis is not None
        try:
            claimed = await self._reclaim()
            if claimed:
                await self._fan_out(claimed)
                return
            resp = await self._redis.xreadgroup(
                self._cfg.group,
                self._cfg.consumer_id,
                streams={self._cfg.stream: ">"},
                count=self._cfg.batch_size,
                block=self._cfg.block_ms,
            )
            if resp:
                # redis-py 8.x stubs annotate xreadgroup as dict-union for RESP3
                # compat; with decode_responses=False (RESP2) the runtime value is
                # always a list of (stream_name, messages) pairs. Narrow explicitly.
                stream_entries: list[StreamMessage] = resp[0][1]  # type: ignore[index,assignment]
                await self._fan_out(stream_entries)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "cts_stream_consumer_tick_error",
                stream=self._cfg.stream,
            )
            await asyncio.sleep(1.0)

    async def _fan_out(self, messages: list[StreamMessage]) -> None:
        assert self._redis is not None
        for message_id, fields in messages:
            msg = self.decode(message_id, fields)
            if msg is None:
                await self._redis.xack(self._cfg.stream, self._cfg.group, message_id)
                continue
            task = asyncio.create_task(self._run_one(message_id, msg))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

    async def _run_one(self, message_id: bytes, msg: T) -> None:
        assert self._redis is not None
        async with self._sem:
            try:
                ok = await self.handle(msg)
            except Exception:
                logger.exception(
                    "cts_stream_consumer_handle_error",
                    stream=self._cfg.stream,
                    message_id=message_id,
                )
                ok = False
        if ok:
            await self._redis.xack(self._cfg.stream, self._cfg.group, message_id)

    async def _reclaim(self) -> list[StreamMessage] | None:
        assert self._redis is not None
        res = await self._redis.xautoclaim(
            self._cfg.stream,
            self._cfg.group,
            self._cfg.consumer_id,
            min_idle_time=self._cfg.reclaim_idle_ms,
            start_id="0",
            count=self._cfg.batch_size,
        )
        if not res or not res[1]:
            return None
        return res[1]

    async def _ensure_group(self) -> None:
        assert self._redis is not None
        try:
            await self._redis.xgroup_create(
                self._cfg.stream,
                self._cfg.group,
                id="$",
                mkstream=True,
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
