"""Unit tests for :class:`~backend.services.cts.subscriber.DementiaSignalSubscriber`.

Tests the decode/handle logic in isolation: no real Redis required.

Covers both the orchestrator-format payload (which uses ``identity_id``,
``signal_kind``, ``context``) and the CC-format payload (backward compat
with ``person_id``, ``signal_type``, ``context_json``).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.models  # noqa: F401
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.subscriber import DementiaSignalSubscriber

# Orchestrator-format signal (what the publisher actually sends).
_ORCHESTRATOR_SIGNAL = {
    "signal_id": "sig-001",
    "identity_id": "grandma",
    "signal_kind": "pacing",
    "severity": "warning",
    "window_start": "2026-04-23T10:00:00+00:00",
    "window_end": "2026-04-23T10:30:00+00:00",
    "value": 7.0,
    "baseline": 2.0,
    "z_score": 2.5,
    "context": {"camera_id": "hallway-1"},
    "emitted_at": "2026-04-23T10:30:00+00:00",
}

# CC-format signal (backward compatibility).
_CC_FORMAT_SIGNAL = {
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
    def test_orchestrator_format_maps_fields(self, subscriber: DementiaSignalSubscriber):
        """Orchestrator field names (identity_id, signal_kind, context) are
        mapped to CC names (person_id, signal_type, context_json)."""
        raw = json.dumps(_ORCHESTRATOR_SIGNAL).encode()
        result = subscriber.decode(b"msg-1", {b"signal": raw})
        assert result is not None
        assert result["person_id"] == "grandma"
        assert result["signal_type"] == "pacing"
        assert result["context_json"] == {"camera_id": "hallway-1"}
        # The original orchestrator names should be removed after mapping.
        assert "identity_id" not in result
        assert "signal_kind" not in result
        assert "context" not in result

    def test_cc_format_still_accepted(self, subscriber: DementiaSignalSubscriber):
        """CC-format signals (backward compat) should decode cleanly."""
        raw = json.dumps(_CC_FORMAT_SIGNAL).encode()
        result = subscriber.decode(b"msg-1", {b"signal": raw})
        assert result is not None
        assert result["person_id"] == "grandma"
        assert result["signal_type"] == "pacing"

    def test_missing_signal_key_returns_none(self, subscriber: DementiaSignalSubscriber):
        result = subscriber.decode(b"msg-1", {b"other": b"data"})
        assert result is None

    def test_invalid_json_returns_none(self, subscriber: DementiaSignalSubscriber):
        result = subscriber.decode(b"msg-1", {b"signal": b"not-json"})
        assert result is None

    def test_missing_required_field_returns_none(self, subscriber: DementiaSignalSubscriber):
        """If an essential field is absent from both naming conventions, decode returns None."""
        # Remove identity_id (and don't provide person_id): should fail.
        incomplete = {k: v for k, v in _ORCHESTRATOR_SIGNAL.items() if k != "identity_id"}
        raw = json.dumps(incomplete).encode()
        result = subscriber.decode(b"msg-1", {b"signal": raw})
        assert result is None

    def test_all_required_fields_present_orchestrator_format(self, subscriber: DementiaSignalSubscriber):
        """Each required field (orchestrator naming) must be present."""
        for field in ("identity_id", "signal_kind", "severity", "window_start", "window_end", "value"):
            incomplete = {k: v for k, v in _ORCHESTRATOR_SIGNAL.items() if k != field}
            raw = json.dumps(incomplete).encode()
            assert subscriber.decode(b"msg-1", {b"signal": raw}) is None, (
                f"Expected None when '{field}' is missing"
            )

    def test_all_required_fields_present_cc_format(self, subscriber: DementiaSignalSubscriber):
        """Each required field (CC naming) must be present."""
        for field in ("person_id", "signal_type", "severity", "window_start", "window_end", "value"):
            incomplete = {k: v for k, v in _CC_FORMAT_SIGNAL.items() if k != field}
            raw = json.dumps(incomplete).encode()
            assert subscriber.decode(b"msg-1", {b"signal": raw}) is None, (
                f"Expected None when '{field}' is missing"
            )


# ---------------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------------


class TestHandle:
    @pytest.mark.asyncio
    async def test_handle_persists_orchestrator_signal(
        self, subscriber: DementiaSignalSubscriber, store: SignalStore
    ):
        """Orchestrator-format signal should be stored with CC-canonical names."""
        # decode maps the fields, then handle persists them.
        raw = json.dumps(_ORCHESTRATOR_SIGNAL).encode()
        decoded = subscriber.decode(b"msg-1", {b"signal": raw})
        assert decoded is not None

        ok = await subscriber.handle(decoded)
        assert ok is True
        results = await store.list_recent()
        assert len(results) == 1
        assert results[0]["signal_type"] == "pacing"
        assert results[0]["person_id"] == "grandma"

    @pytest.mark.asyncio
    async def test_handle_persists_cc_signal(
        self, subscriber: DementiaSignalSubscriber, store: SignalStore
    ):
        """CC-format signal should persist cleanly."""
        ok = await subscriber.handle(_CC_FORMAT_SIGNAL)
        assert ok is True
        results = await store.list_recent()
        assert len(results) == 1
        assert results[0]["signal_type"] == "pacing"

    @pytest.mark.asyncio
    async def test_handle_returns_true_on_success(self, subscriber: DementiaSignalSubscriber):
        ok = await subscriber.handle(_CC_FORMAT_SIGNAL)
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
        await sub.handle(_CC_FORMAT_SIGNAL)
        pipeline.fire_event.assert_awaited_once()
        call_kwargs = pipeline.fire_event.await_args.kwargs
        assert call_kwargs["kind"] == "dementia_signal"
        assert call_kwargs["payload"]["signal_kind"] == "pacing"

    @pytest.mark.asyncio
    async def test_handle_returns_false_on_store_error(self, subscriber: DementiaSignalSubscriber):
        subscriber._store = MagicMock()
        subscriber._store.insert = AsyncMock(side_effect=RuntimeError("db down"))
        ok = await subscriber.handle(_CC_FORMAT_SIGNAL)
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
        ok = await sub.handle(_CC_FORMAT_SIGNAL)
        assert ok is True
