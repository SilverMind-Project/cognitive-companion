"""Tests for WorkflowPipeline concurrent execution limit enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.pipeline import WorkflowExecution
from backend.models.rule import Rule
from backend.models.sensor import Sensor
from backend.services.workflow import WorkflowPipeline

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_sensor(db, sensor_id: str = "cam1") -> Sensor:
    sensor = Sensor(id=sensor_id, name=sensor_id, sensor_type="camera", enabled=True)
    db.add(sensor)
    db.flush()
    return sensor


def _make_rule(
    db,
    name: str = "Test Rule",
    max_concurrent_executions: int = 1,
    **kwargs,
) -> Rule:
    rule = Rule(
        name=name,
        enabled=True,
        trigger_types=["sensor_event"],
        cool_off_minutes=0,
        max_daily_triggers=0,
        max_concurrent_executions=max_concurrent_executions,
        **kwargs,
    )
    db.add(rule)
    db.flush()
    return rule


def _add_running_execution(db, rule: Rule) -> WorkflowExecution:
    """Insert a running WorkflowExecution for *rule*."""
    execution = WorkflowExecution(
        rule_id=rule.id,
        status="running",
        pipeline_data_json={},
    )
    db.add(execution)
    db.flush()
    return execution


def _make_workflow_pipeline(matched_rules):
    """Build a WorkflowPipeline with a rules engine stub and mock executor."""
    rules_engine = AsyncMock()
    rules_engine.get_matching_rules.return_value = matched_rules

    executor = MagicMock()
    execution_stub = MagicMock(spec=WorkflowExecution)
    executor.execute = AsyncMock(return_value=execution_stub)

    return WorkflowPipeline(rules_engine=rules_engine, pipeline_executor=executor), executor


# ---------------------------------------------------------------------------
# concurrent limit -- _concurrent_limit_allows unit tests
# ---------------------------------------------------------------------------


class TestConcurrentLimitAllows:
    def test_unlimited_when_zero(self, db_session):
        """max_concurrent_executions=0 always allows."""
        rule = _make_rule(db_session, max_concurrent_executions=0)
        _add_running_execution(db_session, rule)
        _add_running_execution(db_session, rule)
        db_session.commit()

        pipeline, _ = _make_workflow_pipeline([rule])
        assert pipeline._concurrent_limit_allows(rule, db_session) is True

    def test_allows_when_below_limit(self, db_session):
        """Running count < limit should permit a new execution."""
        rule = _make_rule(db_session, max_concurrent_executions=3)
        _add_running_execution(db_session, rule)
        _add_running_execution(db_session, rule)
        db_session.commit()  # 2 running, limit 3

        pipeline, _ = _make_workflow_pipeline([rule])
        assert pipeline._concurrent_limit_allows(rule, db_session) is True

    def test_blocks_when_at_limit(self, db_session):
        """Running count == limit should block a new execution."""
        rule = _make_rule(db_session, max_concurrent_executions=1)
        _add_running_execution(db_session, rule)
        db_session.commit()

        pipeline, _ = _make_workflow_pipeline([rule])
        assert pipeline._concurrent_limit_allows(rule, db_session) is False

    def test_blocks_when_above_limit(self, db_session):
        """Running count > limit should also block (shouldn't normally happen)."""
        rule = _make_rule(db_session, max_concurrent_executions=1)
        _add_running_execution(db_session, rule)
        _add_running_execution(db_session, rule)
        db_session.commit()

        pipeline, _ = _make_workflow_pipeline([rule])
        assert pipeline._concurrent_limit_allows(rule, db_session) is False

    def test_waiting_executions_count_toward_limit(self, db_session):
        """Waiting executions (e.g. mid-wait-step) also count."""
        rule = _make_rule(db_session, max_concurrent_executions=1)
        waiting = WorkflowExecution(rule_id=rule.id, status="waiting", pipeline_data_json={})
        db_session.add(waiting)
        db_session.commit()

        pipeline, _ = _make_workflow_pipeline([rule])
        assert pipeline._concurrent_limit_allows(rule, db_session) is False

    def test_completed_executions_do_not_count(self, db_session):
        """Only running/waiting statuses consume a concurrency slot."""
        rule = _make_rule(db_session, max_concurrent_executions=1)
        for status in ("completed", "failed", "cancelled"):
            ex = WorkflowExecution(rule_id=rule.id, status=status, pipeline_data_json={})
            db_session.add(ex)
        db_session.commit()

        pipeline, _ = _make_workflow_pipeline([rule])
        assert pipeline._concurrent_limit_allows(rule, db_session) is True

    def test_other_rules_executions_do_not_count(self, db_session):
        """A running execution for rule B must not block rule A."""
        rule_a = _make_rule(db_session, name="Rule A", max_concurrent_executions=1)
        rule_b = _make_rule(db_session, name="Rule B", max_concurrent_executions=1)
        _add_running_execution(db_session, rule_b)
        db_session.commit()

        pipeline, _ = _make_workflow_pipeline([rule_a])
        assert pipeline._concurrent_limit_allows(rule_a, db_session) is True


# ---------------------------------------------------------------------------
# process_event integration: skipped rules produce no task
# ---------------------------------------------------------------------------


class TestProcessEventConcurrencyGating:
    async def test_rule_skipped_when_at_limit(self, db_session, db_factory):
        """process_event must not call executor.execute for a rule at its limit."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_concurrent_executions=1)
        _add_running_execution(db_session, rule)
        db_session.commit()

        pipeline, executor = _make_workflow_pipeline([rule])
        await pipeline.process_event(
            sensor_id=sensor.id,
            media_paths=[],
            media_type="image",
            db=db_session,
        )

        executor.execute.assert_not_awaited()

    async def test_rule_executed_when_below_limit(self, db_session, db_factory):
        """process_event calls executor.execute when slots are available."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_concurrent_executions=2)
        _add_running_execution(db_session, rule)  # 1 running, limit 2
        db_session.commit()

        pipeline, executor = _make_workflow_pipeline([rule])
        await pipeline.process_event(
            sensor_id=sensor.id,
            media_paths=[],
            media_type="image",
            db=db_session,
        )

        executor.execute.assert_awaited_once()

    async def test_multiple_rules_gated_independently(self, db_session, db_factory):
        """Rules with different concurrency states are checked independently."""
        sensor = _make_sensor(db_session)
        rule_free = _make_rule(db_session, name="Free Rule", max_concurrent_executions=1)
        rule_busy = _make_rule(db_session, name="Busy Rule", max_concurrent_executions=1)
        _add_running_execution(db_session, rule_busy)
        db_session.commit()

        # Return both rules from the engine stub
        pipeline, executor = _make_workflow_pipeline([rule_free, rule_busy])
        await pipeline.process_event(
            sensor_id=sensor.id,
            media_paths=[],
            media_type="image",
            db=db_session,
        )

        # executor.execute was called exactly once (for rule_free only)
        assert executor.execute.await_count == 1
        call_args = executor.execute.call_args
        assert call_args.args[0].name == "Free Rule"

    async def test_exception_attributed_to_allowed_rule_not_blocked_rule(self, db_session):
        """Regression: zip was against matched_rules instead of allowed.

        When matched = [blocked, free] and free raises, the old code would zip
        the RuntimeError against blocked (wrong rule) and never process free in
        the loop at all, so the error was logged under the blocked rule's name.
        """
        sensor = _make_sensor(db_session)
        rule_busy = _make_rule(db_session, name="Busy Rule", max_concurrent_executions=1)
        rule_free = _make_rule(db_session, name="Free Rule", max_concurrent_executions=1)
        _add_running_execution(db_session, rule_busy)
        db_session.commit()

        executor = MagicMock()
        executor.execute = AsyncMock(side_effect=RuntimeError("pipeline failed"))
        rules_engine = AsyncMock()
        # Blocked rule comes first -- this is what exposed the zip bug.
        rules_engine.get_matching_rules.return_value = [rule_busy, rule_free]

        pipeline = WorkflowPipeline(rules_engine=rules_engine, pipeline_executor=executor)

        with patch("backend.services.workflow.logger") as mock_logger:
            result = await pipeline.process_event(
                sensor_id=sensor.id, media_paths=[], media_type="image", db=db_session
            )

        assert result == []
        mock_logger.error.assert_called_once()
        error_kwargs = mock_logger.error.call_args.kwargs
        assert error_kwargs["rule_id"] == rule_free.id
        assert error_kwargs["rule"] == "Free Rule"

    async def test_unlimited_rule_always_executes(self, db_session, db_factory):
        """max_concurrent_executions=0 is never blocked."""
        sensor = _make_sensor(db_session)
        rule = _make_rule(db_session, max_concurrent_executions=0)
        for _ in range(5):
            _add_running_execution(db_session, rule)
        db_session.commit()

        pipeline, executor = _make_workflow_pipeline([rule])
        await pipeline.process_event(
            sensor_id=sensor.id,
            media_paths=[],
            media_type="image",
            db=db_session,
        )

        executor.execute.assert_awaited_once()
