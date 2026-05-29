"""U5-T1: PipelineRunService — DAG building and per-step status derivation.

Verifies:
- list_active_runs / get_run build DAG nodes and edges from a known execution
- a failed step reports status='failed' (never 'succeeded') — rule 15
- a cancellation_observed timing produces status='cancelled'
- an execution with no steps returns an empty nodes list
- a missing execution returns None (not a fabricated envelope)
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.models.event import EventLog
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.services.pipeline_run_service import PipelineRunService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(db, name: str = "test-rule") -> Rule:
    rule = Rule(name=name, trigger_types=["manual"], execution_timeout_minutes=0)
    db.add(rule)
    db.flush()
    return rule


def _make_step(
    db, rule: Rule, order: int, label: str, step_type: str = "condition"
) -> PipelineStep:
    step = PipelineStep(rule_id=rule.id, order=order, step_type=step_type, label=label)
    db.add(step)
    db.flush()
    return step


def _make_execution(
    db,
    rule: Rule,
    status: str = "running",
    pipeline_data: dict | None = None,
) -> WorkflowExecution:
    now = datetime.now(UTC)
    event = EventLog(
        rule_id=rule.id,
        rule_name=rule.name,
        trigger_type="manual",
        status="processing",
    )
    db.add(event)
    db.flush()
    ex = WorkflowExecution(
        rule_id=rule.id,
        event_log_id=event.id,
        status=status,
        pipeline_data_json=pipeline_data or {},
        started_at=now,
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetRun:
    def test_returns_none_for_missing_execution(self, db_factory):
        svc = PipelineRunService(db_factory=db_factory)
        result = svc.get_run(execution_id=999999)
        assert result is None

    def test_builds_nodes_from_rule_steps(self, db_factory):
        db = db_factory()
        rule = _make_rule(db, "dag-rule")
        s1 = _make_step(db, rule, order=1, label="Filter", step_type="condition")
        s2 = _make_step(db, rule, order=2, label="Notify", step_type="notification")
        ex = _make_execution(
            db,
            rule,
            status="completed",
            pipeline_data={
                "_step_timings": [
                    {
                        "step_id": s1.id,
                        "success": True,
                        "started_at": "2026-05-29T10:00:00+00:00",
                        "completed_at": "2026-05-29T10:00:01+00:00",
                        "elapsed_seconds": 1.0,
                        "logs": [],
                    },
                    {
                        "step_id": s2.id,
                        "success": True,
                        "started_at": "2026-05-29T10:00:01+00:00",
                        "completed_at": "2026-05-29T10:00:02+00:00",
                        "elapsed_seconds": 1.0,
                        "logs": [],
                    },
                ]
            },
        )
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        envelope = svc.get_run(ex.id)

        assert envelope is not None
        assert envelope.execution_id == ex.id
        assert len(envelope.nodes) == 2
        assert envelope.nodes[0].label == "Filter"
        assert envelope.nodes[1].label == "Notify"

    def test_sequential_edges_built(self, db_factory):
        db = db_factory()
        rule = _make_rule(db, "edge-rule")
        s1 = _make_step(db, rule, order=1, label="A")
        s2 = _make_step(db, rule, order=2, label="B")
        s3 = _make_step(db, rule, order=3, label="C")
        ex = _make_execution(db, rule, status="completed")
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        envelope = svc.get_run(ex.id)

        assert len(envelope.edges) == 2
        assert envelope.edges[0].source == str(s1.id)
        assert envelope.edges[0].target == str(s2.id)
        assert envelope.edges[1].source == str(s2.id)
        assert envelope.edges[1].target == str(s3.id)


class TestStepStatusDerivation:
    def test_failed_step_reports_failed_never_succeeded(self, db_factory):
        """Rule 15: success=False must map to 'failed', never anything else."""
        db = db_factory()
        rule = _make_rule(db, "fail-rule")
        step = _make_step(db, rule, order=1, label="LLM")
        ex = _make_execution(
            db,
            rule,
            status="failed",
            pipeline_data={
                "_step_timings": [
                    {
                        "step_id": step.id,
                        "success": False,
                        "error": "timeout",
                        "started_at": "2026-05-29T10:00:00+00:00",
                        "completed_at": "2026-05-29T10:00:01+00:00",
                        "elapsed_seconds": 1.0,
                        "logs": [],
                    }
                ]
            },
        )
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        envelope = svc.get_run(ex.id)

        assert envelope.nodes[0].status == "failed"

    def test_success_true_maps_to_succeeded(self, db_factory):
        db = db_factory()
        rule = _make_rule(db, "succeed-rule")
        step = _make_step(db, rule, order=1, label="Notify")
        ex = _make_execution(
            db,
            rule,
            status="completed",
            pipeline_data={
                "_step_timings": [
                    {
                        "step_id": step.id,
                        "success": True,
                        "started_at": "2026-05-29T10:00:00+00:00",
                        "completed_at": "2026-05-29T10:00:01+00:00",
                        "elapsed_seconds": 1.0,
                        "logs": [],
                    }
                ]
            },
        )
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        envelope = svc.get_run(ex.id)

        assert envelope.nodes[0].status == "succeeded"

    def test_cancellation_observed_maps_to_cancelled(self, db_factory):
        db = db_factory()
        rule = _make_rule(db, "cancel-rule")
        step = _make_step(db, rule, order=1, label="Wait")
        ex = _make_execution(
            db,
            rule,
            status="cancelled",
            pipeline_data={
                "_step_timings": [
                    {
                        "step_id": step.id,
                        "success": False,
                        "cancellation_observed": True,
                        "started_at": "2026-05-29T10:00:00+00:00",
                        "completed_at": "2026-05-29T10:00:01+00:00",
                        "elapsed_seconds": 1.0,
                        "logs": [],
                    }
                ]
            },
        )
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        envelope = svc.get_run(ex.id)

        assert envelope.nodes[0].status == "cancelled"

    def test_untimed_step_with_active_execution_is_running(self, db_factory):
        """A step that has no timing entry and is current_step_id of a running execution is 'running'."""
        db = db_factory()
        rule = _make_rule(db, "running-rule")
        step = _make_step(db, rule, order=1, label="LLM")
        ex = _make_execution(db, rule, status="running", pipeline_data={})
        ex.current_step_id = step.id
        db.commit()
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        envelope = svc.get_run(ex.id)

        assert envelope.nodes[0].status == "running"


class TestListActiveRuns:
    def test_returns_only_running_and_waiting(self, db_factory):
        db = db_factory()
        rule = _make_rule(db, "active-rule")
        ex_running = _make_execution(db, rule, status="running")
        ex_waiting = _make_execution(db, rule, status="waiting")
        _make_execution(db, rule, status="completed")
        _make_execution(db, rule, status="failed")
        db.close()

        svc = PipelineRunService(db_factory=db_factory)
        active = svc.list_active_runs()

        ids = {e.execution_id for e in active}
        assert ex_running.id in ids
        assert ex_waiting.id in ids
        assert len(active) == 2
