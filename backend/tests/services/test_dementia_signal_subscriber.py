"""Unit tests for :class:`DementiaSignalSubscriber` (proto wire format)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.models  # noqa: F401
from backend.integrations.proto.continuoustracking.v1 import (  # type: ignore[attr-defined]
    signals_pb2,
)
from backend.models.person import HouseholdMember
from backend.services.cts.signal_store import SignalStore
from backend.services.cts.subscriber import DementiaSignalSubscriber


def _proto_signal(
    *,
    identity_id: str = "grandma",
    kind: int = signals_pb2.DEMENTIA_SIGNAL_KIND_PACING,
    severity: int = signals_pb2.DEMENTIA_SIGNAL_SEVERITY_WARNING,
    value: float = 7.0,
    has_baseline: bool = True,
    baseline: float = 2.0,
    has_z_score: bool = True,
    z_score: float = 2.5,
    context: dict | None = None,
) -> signals_pb2.DementiaSignal:
    return signals_pb2.DementiaSignal(
        signal_id="sig-001",
        identity_id=identity_id,
        kind=kind,
        severity=severity,
        value=value,
        has_baseline=has_baseline,
        baseline=baseline,
        has_z_score=has_z_score,
        z_score=z_score,
        window_start_unix_ns=1735305600000000000,
        window_end_unix_ns=1735305600000000000 + 30 * 60 * 1_000_000_000,
        emitted_at_unix_ns=1735305600000000000 + 30 * 60 * 1_000_000_000,
        context_json=json.dumps(context or {"camera_id": "hallway-1"}),
    )


def _proto_fields(message: signals_pb2.DementiaSignal) -> dict[bytes, bytes]:
    return {b"signal": message.SerializeToString()}


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
    def test_proto_signal_maps_to_cc_dict(self, subscriber: DementiaSignalSubscriber):
        result = subscriber.decode(b"msg-1", _proto_fields(_proto_signal()))
        assert result is not None
        assert result["person_id"] == "grandma"
        assert result["signal_type"] == "pacing"
        assert result["severity"] == "warning"
        assert result["value"] == pytest.approx(7.0)
        assert result["baseline"] == pytest.approx(2.0)
        assert result["z_score"] == pytest.approx(2.5)
        assert result["context_json"] == {"camera_id": "hallway-1"}

    def test_optional_baseline_and_z_score_become_none(self, subscriber: DementiaSignalSubscriber):
        message = _proto_signal(has_baseline=False, baseline=0.0, has_z_score=False, z_score=0.0)
        result = subscriber.decode(b"msg-1", _proto_fields(message))
        assert result is not None
        assert result["baseline"] is None
        assert result["z_score"] is None

    def test_missing_signal_field_returns_none(self, subscriber: DementiaSignalSubscriber):
        assert subscriber.decode(b"msg-1", {b"other": b"x"}) is None

    def test_invalid_proto_returns_none(self, subscriber: DementiaSignalSubscriber):
        assert subscriber.decode(b"msg-1", {b"signal": b"not-protobuf-\xff\x01"}) is None

    def test_unknown_kind_enum_returns_none(self, subscriber: DementiaSignalSubscriber):
        message = _proto_signal(kind=signals_pb2.DEMENTIA_SIGNAL_KIND_UNSPECIFIED)
        assert subscriber.decode(b"msg-1", _proto_fields(message)) is None

    def test_missing_identity_returns_none(self, subscriber: DementiaSignalSubscriber):
        message = _proto_signal(identity_id="")
        assert subscriber.decode(b"msg-1", _proto_fields(message)) is None

    def test_fall_suspected_kind_decodes(self, subscriber: DementiaSignalSubscriber):
        # Proto enum value 7 = DEMENTIA_SIGNAL_KIND_FALL_SUSPECTED (M2 task 2.2).
        message = _proto_signal(
            kind=7,
            severity=signals_pb2.DEMENTIA_SIGNAL_SEVERITY_WARNING,
        )
        result = subscriber.decode(b"msg-fall-1", _proto_fields(message))
        assert result is not None
        assert result["signal_type"] == "fall_suspected"
        assert result["severity"] == "warning"


# ---------------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------------


class TestHandle:
    @pytest.mark.asyncio
    async def test_handle_persists_signal(
        self, subscriber: DementiaSignalSubscriber, store: SignalStore
    ):
        decoded = subscriber.decode(b"msg-1", _proto_fields(_proto_signal()))
        assert decoded is not None
        ok = await subscriber.handle(decoded)
        assert ok is True

        results, _ = await store.list_recent()
        assert len(results) == 1
        assert results[0]["signal_type"] == "pacing"
        assert results[0]["person_id"] == "grandma"

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
        decoded = sub.decode(b"msg-1", _proto_fields(_proto_signal()))
        assert decoded is not None
        await sub.handle(decoded)
        pipeline.fire_event.assert_awaited_once()
        call_kwargs = pipeline.fire_event.await_args.kwargs
        assert call_kwargs["kind"] == "dementia_signal"
        assert call_kwargs["payload"]["signal_kind"] == "pacing"

    @pytest.mark.asyncio
    async def test_handle_returns_false_on_store_error(self, subscriber: DementiaSignalSubscriber):
        subscriber._store = MagicMock()
        subscriber._store.insert = AsyncMock(side_effect=RuntimeError("db down"))
        decoded = subscriber.decode(b"msg-1", _proto_fields(_proto_signal()))
        assert decoded is not None
        ok = await subscriber.handle(decoded)
        assert ok is False

    @pytest.mark.asyncio
    async def test_handle_persists_fall_suspected_signal(
        self, subscriber: DementiaSignalSubscriber, store: SignalStore
    ):
        message = _proto_signal(
            kind=7,
            severity=signals_pb2.DEMENTIA_SIGNAL_SEVERITY_WARNING,
            identity_id="grandma",
        )
        decoded = subscriber.decode(b"msg-fall-1", _proto_fields(message))
        assert decoded is not None
        ok = await subscriber.handle(decoded)
        assert ok is True

        results, _ = await store.list_recent()
        assert any(r["signal_type"] == "fall_suspected" for r in results)

    @pytest.mark.asyncio
    async def test_pipeline_error_does_not_fail_handle(self, store: SignalStore):
        pipeline = MagicMock()
        pipeline.fire_event = AsyncMock(side_effect=RuntimeError("pipeline down"))
        sub = DementiaSignalSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",
            store=store,
            pipeline=pipeline,
        )
        decoded = sub.decode(b"msg-1", _proto_fields(_proto_signal()))
        assert decoded is not None
        ok = await sub.handle(decoded)
        assert ok is True


class TestDispatchSuppression:
    """Dispatch is suppressed when the person's cts_alert_config disables the kind."""

    @pytest.mark.asyncio
    async def test_dispatch_suppressed_when_kind_disabled(self, store: SignalStore, db_factory):
        """Signal is stored but pipeline.fire_event is NOT called when kind is disabled."""
        db = db_factory()
        member = HouseholdMember(
            id="grandma",
            name="Grandma",
            cts_alert_config={"enabled_kinds": ["absence"], "min_severity": "info"},
        )
        db.add(member)
        db.commit()
        db.close()

        pipeline = MagicMock()
        pipeline.fire_event = AsyncMock()
        sub = DementiaSignalSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",
            store=store,
            pipeline=pipeline,
            db_factory=db_factory,
        )
        decoded = sub.decode(
            b"msg-1", _proto_fields(_proto_signal(kind=signals_pb2.DEMENTIA_SIGNAL_KIND_PACING))
        )
        assert decoded is not None
        ok = await sub.handle(decoded)
        assert ok is True
        # Signal should be persisted
        results, _ = await store.list_recent()
        assert len(results) == 1
        # But pipeline should NOT be fired
        pipeline.fire_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_allowed_when_kind_enabled(self, store: SignalStore, db_factory):
        """Pipeline is fired when the kind is in the person's enabled_kinds."""
        db = db_factory()
        member = HouseholdMember(
            id="grandma",
            name="Grandma",
            cts_alert_config={"enabled_kinds": ["pacing", "absence"], "min_severity": "info"},
        )
        db.add(member)
        db.commit()
        db.close()

        pipeline = MagicMock()
        pipeline.fire_event = AsyncMock()
        sub = DementiaSignalSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",
            store=store,
            pipeline=pipeline,
            db_factory=db_factory,
        )
        decoded = sub.decode(
            b"msg-1", _proto_fields(_proto_signal(kind=signals_pb2.DEMENTIA_SIGNAL_KIND_PACING))
        )
        assert decoded is not None
        await sub.handle(decoded)
        pipeline.fire_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_allowed_when_no_member_config(self, store: SignalStore, db_factory):
        """Unknown person (no DB record) gets permissive default: dispatch proceeds."""
        pipeline = MagicMock()
        pipeline.fire_event = AsyncMock()
        sub = DementiaSignalSubscriber(
            redis_url="redis://localhost:6379",
            consumer_id="test",
            store=store,
            pipeline=pipeline,
            db_factory=db_factory,
        )
        decoded = sub.decode(b"msg-1", _proto_fields(_proto_signal(identity_id="unknown-person")))
        assert decoded is not None
        await sub.handle(decoded)
        pipeline.fire_event.assert_awaited_once()
