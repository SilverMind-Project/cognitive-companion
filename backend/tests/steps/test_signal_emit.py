"""Unit tests for backend.steps.builtin.signal_emit.SignalEmitHandler."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock

import pytest

from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.signal_emit import SignalEmitHandler


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)
    id: int = 1
    label: str = "signal_emit_1"
    rule_id: int = 42


@dataclass
class _FakeExecution:
    id: int = 100
    rule_id: int = 42


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="cron", sensor_id="cam-1", room_name="kitchen")


def _make_services(signals=None) -> ServiceContainer:
    return ServiceContainer(db_factory=lambda: None, signals=signals)


def _make_signals(result: dict | None = None) -> AsyncMock:
    signals = AsyncMock()
    signals.emit = AsyncMock(
        return_value=result or {"emitted": True, "reason": None, "signal_row_id": 7}
    )
    return signals


@pytest.mark.asyncio
async def test_emits_with_correct_kind_person_severity_context():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(
        config_json={
            "kind": "tea_intent_suspected",
            "person_id": "grandma",
            "severity": "warning",
            "value": 0.82,
            "context": {"reason": "hand near kettle"},
            "dedupe_minutes": 45,
        }
    )

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert result.success is True
    assert result.data["emitted"] is True
    assert result.data["reason"] is None
    assert result.data["signal_row_id"] == 7
    signals.emit.assert_called_once()
    call_kwargs = signals.emit.call_args.kwargs
    assert call_kwargs["signal_kind"] == "tea_intent_suspected"
    assert call_kwargs["person_id"] == "grandma"
    assert call_kwargs["severity"] == "warning"
    assert call_kwargs["value"] == 0.82
    assert call_kwargs["context"]["reason"] == "hand near kettle"
    assert call_kwargs["context"]["rule_id"] == 42
    assert call_kwargs["context"]["execution_id"] == 100
    assert call_kwargs["dedupe_minutes"] == 45
    assert_output_conforms_to_schema(handler, result)


@pytest.mark.asyncio
async def test_forged_cts_kind_rejected_at_execute_time():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "fall_suspected", "person_id": "grandma"})

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert result.success is False
    assert result.data == {"emitted": False, "reason": "invalid_kind", "signal_row_id": None}
    signals.emit.assert_not_called()


@pytest.mark.asyncio
async def test_missing_signals_service_degrades_to_unavailable():
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "tea_intent_suspected", "person_id": "grandma"})

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=None)
    )

    assert result.success is True
    assert result.data == {"emitted": False, "reason": "unavailable", "signal_row_id": None}


@pytest.mark.asyncio
async def test_missing_person_id_fails_without_calling_signals():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "tea_intent_suspected"})

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert result.success is False
    assert result.data["reason"] == "no_person_id"
    signals.emit.assert_not_called()


@pytest.mark.asyncio
async def test_person_id_falls_back_to_pipeline_data():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "tea_intent_suspected"})
    pipeline_data = {"person_id": "grandma"}

    await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services(signals=signals)
    )

    assert signals.emit.call_args.kwargs["person_id"] == "grandma"


@pytest.mark.asyncio
async def test_dedupe_reason_passed_through_result():
    signals = _make_signals({"emitted": False, "reason": "deduped", "signal_row_id": None})
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "tea_intent_suspected", "person_id": "grandma"})

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert result.data == {"emitted": False, "reason": "deduped", "signal_row_id": None}


@pytest.mark.asyncio
async def test_value_template_resolves_from_upstream_step_output():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(
        config_json={
            "kind": "tea_intent_suspected",
            "person_id": "grandma",
            "value": "{{ steps.tea_verdict.outputs.confidence }}",
        }
    )
    pipeline_data = {"steps": {"tea_verdict": {"outputs": {"confidence": 0.73}}}}

    await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services(signals=signals)
    )

    assert signals.emit.call_args.kwargs["value"] == 0.73


@pytest.mark.asyncio
async def test_unresolvable_value_template_defaults_to_one():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(
        config_json={
            "kind": "tea_intent_suspected",
            "person_id": "grandma",
            "value": "{{ steps.missing.outputs.confidence }}",
        }
    )

    await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert signals.emit.call_args.kwargs["value"] == 1.0


def test_metadata_is_action_and_not_gate_safe():
    meta = SignalEmitHandler.metadata()
    assert meta.type_name == "signal_emit"
    assert meta.category == "action"
    assert meta.gate_safe is False
    assert meta.gate_only is False


def test_metadata_kind_enum_excludes_cts_produced_kinds():
    meta = SignalEmitHandler.metadata()
    kind_enum = meta.config_schema["properties"]["kind"]["enum"]
    assert "fall_suspected" not in kind_enum
    assert "tea_intent_suspected" in kind_enum


@pytest.mark.asyncio
async def test_trigger_cooloff_armed_on_successful_emit_by_default():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "tea_intent_suspected", "person_id": "grandma"})

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert result.data["_cooloff_triggered"] is True


@pytest.mark.asyncio
async def test_trigger_cooloff_disabled_by_config():
    signals = _make_signals()
    handler = SignalEmitHandler()
    step = _FakeStep(
        config_json={
            "kind": "tea_intent_suspected",
            "person_id": "grandma",
            "trigger_cooloff": False,
        }
    )

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert "_cooloff_triggered" not in result.data


@pytest.mark.asyncio
async def test_trigger_cooloff_not_armed_when_deduped():
    signals = _make_signals({"emitted": False, "reason": "deduped", "signal_row_id": None})
    handler = SignalEmitHandler()
    step = _FakeStep(config_json={"kind": "tea_intent_suspected", "person_id": "grandma"})

    result = await handler.execute(
        step, _FakeExecution(), {}, _make_trigger(), _make_services(signals=signals)
    )

    assert "_cooloff_triggered" not in result.data
