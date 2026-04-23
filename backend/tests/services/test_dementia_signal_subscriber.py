"""Unit tests for :class:`~backend.services.cts.subscriber.DementiaSignalSubscriber`.

Tests the decode/handle logic in isolation — no real Redis required.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.models  # noqa: F401
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.subscriber import DementiaSignalSubscriber

_VALID_SIGNAL = {
    "person_id": "grandma",
    "signal_type": "pacing",
    "severity": "warning",
    "window_start": "2026-04-23T10:00:00+00:00",
    "window_end": "2026-04-23T10:30:00+00:00",
    "value": 7.0,
}


@pytest.fixture
def store(db_factory) -> SignalStore:
    return SignalStore(db_factory=db_factory)


@pytest.fixture
def subscriber(store: SignalStore) -> DementiaSignalSubscriber:
    return DementiaSignalSubscriber(
        redis_url="redis://localhost:6379",
        consumer_id="test-consumer",
        store=store,
        pipeline=None,
    )


# ---------------------------------------------------------------------------
# decode
# ---------------------------------------------------------------------------


class TestDecode:
    def test_valid_json_returns_dict(self, subscriber: DementiaSignalSubscriber):
        raw = json.dumps(_VALID_SIGNAL).encode()
        result = subscriber.decode(b"msg-1", {b"signal": raw})
        assert result is not None
        assert result["person_id"] == "grandma"

    def test_missing_signal_key_returns_none(self, subscriber: DementiaSignalSubscriber):
        result = subscriber.decode(b"msg-1", {b"other": b"data"})
        assert result is None

    def test_invalid_json_returns_none(self, subscriber: DementiaSignalSubscriber):
        result = subscriber.decode(b"msg-1", {b"signal": b"not-json"})
        assert result is None

    def test_missing_required_field_returns_none(self, subscriber: DementiaSignalSubscriber):
        incomplete = {k: v for k, v in _VALID_SIGNAL.items() if k != "person_id"}
        raw = json.dumps(incomplete).encode()
        result = subscriber.decode(b"msg-1", {b"signal": raw})
        assert result is None

    def test_all_required_fields_present(self, subscriber: DementiaSignalSubscriber):
        """All six required fields must be present for decode to succeed."""
        for field in ("person_id", "signal_type", "severity", "window_start", "window_end", "value"):
            incomplete = {k: v for k, v in _VALID_SIGNAL.items() if k != field}
            raw = json.dumps(incomplete).encode()
            assert subscriber.decode(b"msg-1", {b"signal": raw}) is None


# ---------------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------------


class TestHandle:
    @pytest.mark.asyncio
    async def test_handle_persists_signal(self, subscriber: DementiaSignalSubscriber, store: SignalStore):
        ok = await subscriber.handle(_VALID_SIGNAL)
        assert ok is True
        results = await store.list_recent()
        assert len(results) == 1
        assert results[0]["signal_type"] == "pacing"

    @pytest.mark.asyncio
    async def test_handle_returns_true_on_success(self, subscriber: DementiaSignalSubscriber):
        ok = await subscriber.handle(_VALID_SIGNAL)
        assert ok is True

    @pytest.mark.asyncio
    async def test_handle_fires_pipeline_event(self, store: SignalStore):
        pipeline = MagicMock()
        pipeline.fire_event = AsyncMock()
        sub = DementiaSignalSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",
            store=store,
            pipeline=pipeline,
        )
        await sub.handle(_VALID_SIGNAL)
        pipeline.fire_event.assert_awaited_once()
        call_kwargs = pipeline.fire_event.await_args.kwargs
        assert call_kwargs["kind"] == "dementia_signal"
        assert call_kwargs["payload"]["signal_kind"] == "pacing"

    @pytest.mark.asyncio
    async def test_handle_returns_false_on_store_error(self, subscriber: DementiaSignalSubscriber):
        subscriber._store = MagicMock()
        subscriber._store.insert = AsyncMock(side_effect=RuntimeError("db down"))
        ok = await subscriber.handle(_VALID_SIGNAL)
        assert ok is False

    @pytest.mark.asyncio
    async def test_pipeline_error_does_not_fail_handle(self, store: SignalStore):
        """A pipeline fire_event error must not cause handle() to return False."""
        pipeline = MagicMock()
        pipeline.fire_event = AsyncMock(side_effect=RuntimeError("pipeline down"))
        sub = DementiaSignalSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",
            store=store,
            pipeline=pipeline,
        )
        ok = await sub.handle(_VALID_SIGNAL)
        assert ok is True
