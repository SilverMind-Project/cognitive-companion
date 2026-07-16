"""C6 regression: fire_event dispatches matched rules concurrently.

Before M13, fire_event awaited each matched rule's execute() serially in a
loop, so one slow rule delayed every other rule for the same CTS event. This
mirrors the concurrent-dispatch pattern WorkflowPipeline.process_event
already used (asyncio.gather with per-rule DB sessions and per-rule
exception isolation).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule
from backend.steps.base import ServiceContainer, StepResult


def _make_rule(db, name, **kwargs):
    rule = Rule(name=name, enabled=True, trigger_types=["dementia_signal"], **kwargs)
    db.add(rule)
    db.flush()
    return rule


def _make_step(db, rule, step_type="notification", label="step_1"):
    step = PipelineStep(
        rule_id=rule.id,
        order=1,
        step_type=step_type,
        label=label,
        config_json={},
        enabled=True,
    )
    db.add(step)
    db.flush()
    return step


@pytest.mark.asyncio
async def test_fire_event_dispatches_matched_rules_concurrently(db_session, db_factory):
    from backend.services.pipeline_executor import PipelineExecutor

    rule_a = _make_rule(db_session, "Rule A")
    _make_step(db_session, rule_a)
    rule_b = _make_rule(db_session, "Rule B")
    _make_step(db_session, rule_b)
    db_session.commit()

    gate = asyncio.Event()
    order: list[str] = []

    async def mock_execute_step(step, execution, pipeline_data, trigger):
        if trigger.trigger_type == "dementia_signal" and execution.rule_id == rule_a.id:
            # Rule A blocks until Rule B has already started -- only
            # possible under concurrent dispatch, not a serial loop.
            order.append("a_start")
            await asyncio.wait_for(gate.wait(), timeout=2.0)
            order.append("a_end")
        else:
            order.append("b_start")
            gate.set()
            order.append("b_end")
        return StepResult(success=True)

    rules_engine = MagicMock()
    rules_engine.get_matching_rules_for_event = AsyncMock(return_value=[rule_a, rule_b])

    executor = PipelineExecutor(
        ServiceContainer(db_factory=db_factory),
        rules_engine=rules_engine,
    )

    with patch.object(executor, "_execute_step", side_effect=mock_execute_step):
        await asyncio.wait_for(
            executor.fire_event(source="test", kind="dementia_signal", payload={}),
            timeout=3.0,
        )

    assert order[0] == "a_start"
    assert "b_start" in order
    assert order[-1] == "a_end"


@pytest.mark.asyncio
async def test_fire_event_one_rule_failure_does_not_affect_other(db_session, db_factory):
    from backend.services.pipeline_executor import PipelineExecutor

    rule_a = _make_rule(db_session, "Rule A")
    _make_step(db_session, rule_a, step_type="bad_step")
    rule_b = _make_rule(db_session, "Rule B")
    _make_step(db_session, rule_b)
    db_session.commit()

    rules_engine = MagicMock()
    rules_engine.get_matching_rules_for_event = AsyncMock(return_value=[rule_a, rule_b])

    executor = PipelineExecutor(
        ServiceContainer(db_factory=db_factory),
        rules_engine=rules_engine,
    )

    await executor.fire_event(source="test", kind="dementia_signal", payload={})

    db = db_factory()
    try:
        from backend.models.pipeline import WorkflowExecution

        executions = db.query(WorkflowExecution).all()
        by_rule = {e.rule_id: e.status for e in executions}
        assert by_rule[rule_a.id] == "failed"
        assert by_rule[rule_b.id] == "completed"
    finally:
        db.close()
