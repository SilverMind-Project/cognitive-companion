"""Tests for workflow execution detail observability contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule
from backend.routers.workflows import get_execution_detail, rerun_execution
from backend.schemas.workflow import RerunRequest


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _make_rule(db_session) -> Rule:
    rule = Rule(name="Branching Rule", enabled=True, trigger_types=["manual"])
    db_session.add(rule)
    db_session.flush()
    return rule


def _make_execution(db_session, rule: Rule, pipeline_data: dict, status: str = "completed"):
    execution = WorkflowExecution(
        rule_id=rule.id,
        status=status,
        pipeline_data_json=pipeline_data,
    )
    db_session.add(execution)
    db_session.commit()
    return execution


def test_detail_returns_graph_and_output_ports(db_session):
    rule = _make_rule(db_session)
    execution = _make_execution(
        db_session,
        rule,
        {
            "trigger": {"type": "manual"},
            "steps": {"Condition": {"outputs": {"matched": True}}},
            "_graph": {
                "steps": [
                    {
                        "id": 1,
                        "label": "Condition",
                        "step_type": "condition",
                        "position_x": 10,
                        "position_y": 20,
                        "output_ports": ["true", "false"],
                    }
                ],
                "edges": [],
            },
            "_step_timings": [
                {
                    "step_id": 1,
                    "step_type": "condition",
                    "label": "Condition",
                    "started_at": _iso_now(),
                    "completed_at": _iso_now(),
                    "elapsed_seconds": 0.1,
                    "success": True,
                    "output_port": "true",
                }
            ],
        },
    )

    detail = get_execution_detail(execution.id, db=db_session)

    assert detail.graph is not None
    assert detail.graph.steps[0].output_ports == ["true", "false"]
    assert detail.timeline[0].step_id == 1
    assert detail.timeline[0].output_port == "true"
    assert detail.timeline[0].outputs == {"matched": True}


def test_detail_marks_untaken_branch_step_skipped(db_session):
    rule = _make_rule(db_session)
    execution = _make_execution(
        db_session,
        rule,
        {
            "trigger": {"type": "manual"},
            "steps": {},
            "_graph": {
                "steps": [
                    {
                        "id": 1,
                        "label": "Condition",
                        "step_type": "condition",
                        "output_ports": ["true", "false"],
                    },
                    {
                        "id": 2,
                        "label": "True Notify",
                        "step_type": "notification",
                        "output_ports": ["main"],
                    },
                    {
                        "id": 3,
                        "label": "False Notify",
                        "step_type": "notification",
                        "output_ports": ["main"],
                    },
                ],
                "edges": [
                    {
                        "source_step_id": 1,
                        "source_port": "true",
                        "target_step_id": 2,
                        "target_port": "main",
                    },
                    {
                        "source_step_id": 1,
                        "source_port": "false",
                        "target_step_id": 3,
                        "target_port": "main",
                    },
                ],
            },
            "_step_timings": [
                {
                    "step_id": 1,
                    "step_type": "condition",
                    "label": "Condition",
                    "started_at": _iso_now(),
                    "completed_at": _iso_now(),
                    "elapsed_seconds": 0.1,
                    "success": True,
                    "output_port": "true",
                },
                {
                    "step_id": 2,
                    "step_type": "notification",
                    "label": "True Notify",
                    "started_at": _iso_now(),
                    "completed_at": _iso_now(),
                    "elapsed_seconds": 0.1,
                    "success": True,
                    "output_port": "main",
                },
            ],
        },
    )

    detail = get_execution_detail(execution.id, db=db_session)

    status_by_id = {entry.step_id: entry.status for entry in detail.timeline}
    assert status_by_id[2] == "success"
    assert status_by_id[3] == "skipped"


def test_detail_graph_null_for_pre_snapshot_execution(db_session):
    rule = _make_rule(db_session)
    execution = _make_execution(
        db_session,
        rule,
        {
            "trigger": {"type": "manual"},
            "steps": {},
            "_step_timings": [],
        },
    )

    detail = get_execution_detail(execution.id, db=db_session)

    assert detail.graph is None
    assert detail.timeline == []


async def test_rerun_returns_new_execution_id_and_rule_id(db_session):
    rule = _make_rule(db_session)
    execution = _make_execution(
        db_session,
        rule,
        {"trigger": {"type": "manual"}, "steps": {}, "_step_timings": []},
    )
    new_execution = SimpleNamespace(id=99, rule_id=rule.id, status="running")
    pipeline_executor = SimpleNamespace(execute=AsyncMock(return_value=new_execution))
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pipeline_executor=pipeline_executor))
    )

    result = await rerun_execution(
        execution.id,
        RerunRequest(),
        request=request,
        db=db_session,
    )

    assert result == {"execution_id": 99, "rule_id": rule.id, "status": "running"}
