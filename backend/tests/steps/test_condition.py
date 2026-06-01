"""Tests for the condition step handler."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from backend.steps.base import TriggerContext
from backend.steps.builtin.condition import ConditionHandler


@dataclass
class _FakeStep:
    id: int = 1
    step_type: str = "condition"
    label: str = "condition_1"
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


async def test_condition_true_returns_true_port():
    handler = ConditionHandler()
    step = _FakeStep(config_json={"expression": "true"})

    result = await handler.execute(step, _FakeExecution(), {}, _trigger(), MagicMock())

    assert result.output_ports == ("true",)
    assert result.should_continue is True
    assert result.data["condition"]["result"] is True


async def test_condition_false_returns_false_port():
    handler = ConditionHandler()
    step = _FakeStep(config_json={"expression": "false"})

    result = await handler.execute(step, _FakeExecution(), {}, _trigger(), MagicMock())

    assert result.output_ports == ("false",)
    assert result.should_continue is True
    assert result.data["condition"]["result"] is False


async def test_condition_trigger_cooloff_sets_flag_on_true():
    handler = ConditionHandler()
    step = _FakeStep(config_json={"expression": "true", "trigger_cooloff": True})

    result = await handler.execute(step, _FakeExecution(), {}, _trigger(), MagicMock())

    assert result.data["_cooloff_triggered"] is True


async def test_condition_strips_template_braces():
    handler = ConditionHandler()
    step = _FakeStep(config_json={"expression": "{{ true }}"})

    result = await handler.execute(step, _FakeExecution(), {}, _trigger(), MagicMock())

    assert result.output_ports == ("true",)
    assert result.data["condition"]["expression"] == "true"
