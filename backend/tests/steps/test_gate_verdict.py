"""Tests for the gate_verdict step handler."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from unittest.mock import MagicMock

from backend.steps.base import TriggerContext
from backend.steps.builtin.gate_verdict import GateVerdictHandler


@dataclass
class _FakeStep:
    id: int = 1
    step_type: str = "gate_verdict"
    label: str = "gate_verdict_1"
    config_json: dict | None = None
    order: int = 0
    enabled: bool = True


@dataclass
class _FakeExecution:
    id: int = 1
    status: str = "running"
    pipeline_data_json: dict | None = None
    current_step_id: int | None = None
    error: str | None = None


def _trigger() -> TriggerContext:
    return TriggerContext(trigger_type="manual")


async def test_complete_when_expression_true_and_confidence_high():
    handler = GateVerdictHandler()
    step = _FakeStep(
        config_json={
            "complete_if": "steps.vlm.outputs.complete",
            "confidence_path": "steps.vlm.outputs.confidence",
            "reason_path": "steps.vlm.outputs.reason",
            "min_confidence": 0.5,
        }
    )
    pipeline_data = {
        "steps": {
            "vlm": {
                "outputs": {
                    "complete": True,
                    "confidence": 0.8,
                    "reason": "Kettle is on hob",
                }
            }
        }
    }

    result = await handler.execute(step, _FakeExecution(), pipeline_data, _trigger(), MagicMock())

    assert result.should_continue is True
    assert result.output_ports == ("main",)
    verdict = result.data["gate_verdict"]
    assert verdict["complete"] is True
    assert verdict["confidence"] == 0.8
    assert verdict["reason"] == "Kettle is on hob"


async def test_not_complete_when_expression_false():
    handler = GateVerdictHandler()
    step = _FakeStep(
        config_json={
            "complete_if": "steps.vlm.outputs.complete",
            "confidence_path": "steps.vlm.outputs.confidence",
            "reason_path": "steps.vlm.outputs.reason",
        }
    )
    pipeline_data = {
        "steps": {
            "vlm": {
                "outputs": {
                    "complete": False,
                    "confidence": 0.9,
                    "reason": "Kettle is not on hob",
                }
            }
        }
    }

    result = await handler.execute(step, _FakeExecution(), pipeline_data, _trigger(), MagicMock())

    verdict = result.data["gate_verdict"]
    assert verdict["complete"] is False
    assert verdict["confidence"] == 0.9
    assert verdict["reason"] == "Kettle is not on hob"


async def test_low_confidence_fails_closed():
    handler = GateVerdictHandler()
    step = _FakeStep(
        config_json={
            "complete_if": "steps.vlm.outputs.complete",
            "confidence_path": "steps.vlm.outputs.confidence",
            "reason_path": "steps.vlm.outputs.reason",
            "min_confidence": 0.7,
        }
    )
    # Even if complete is True, confidence 0.5 < min_confidence 0.7 triggers fail-closed (complete=False, reason="low_confidence")
    pipeline_data = {
        "steps": {
            "vlm": {
                "outputs": {
                    "complete": True,
                    "confidence": 0.5,
                    "reason": "Might be a kettle",
                }
            }
        }
    }

    result = await handler.execute(step, _FakeExecution(), pipeline_data, _trigger(), MagicMock())

    verdict = result.data["gate_verdict"]
    assert verdict["complete"] is False
    assert verdict["confidence"] == 0.5
    assert verdict["reason"] == "low_confidence"


async def test_missing_confidence_path_defaults_zero():
    handler = GateVerdictHandler()
    step = _FakeStep(
        config_json={
            "complete_if": "true",
            "confidence_path": "steps.vlm.outputs.missing_confidence",
        }
    )
    pipeline_data = {}

    result = await handler.execute(step, _FakeExecution(), pipeline_data, _trigger(), MagicMock())

    verdict = result.data["gate_verdict"]
    assert verdict["confidence"] == 0.0


async def test_expression_error_fails_closed_and_logs(caplog):
    handler = GateVerdictHandler()
    step = _FakeStep(
        config_json={
            "complete_if": "steps.vlm.outputs.non_existent_key.nested",
        }
    )
    pipeline_data = {}

    with caplog.at_level(logging.ERROR):
        result = await handler.execute(
            step, _FakeExecution(), pipeline_data, _trigger(), MagicMock()
        )

    verdict = result.data["gate_verdict"]
    assert verdict["complete"] is False
    assert any("gate_verdict_eval_failed" in record.message for record in caplog.records)


async def test_writes_gate_verdict_key_with_clamped_confidence():
    handler = GateVerdictHandler()
    step = _FakeStep(
        config_json={
            "complete_if": "true",
            "confidence_path": "conf",
        }
    )

    # Confidence is 1.5, should be clamped to 1.0
    result = await handler.execute(step, _FakeExecution(), {"conf": 1.5}, _trigger(), MagicMock())
    assert result.data["gate_verdict"]["confidence"] == 1.0

    # Confidence is -0.5, should be clamped to 0.0
    result = await handler.execute(step, _FakeExecution(), {"conf": -0.5}, _trigger(), MagicMock())
    assert result.data["gate_verdict"]["confidence"] == 0.0
