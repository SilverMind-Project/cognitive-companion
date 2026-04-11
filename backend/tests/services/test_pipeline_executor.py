"""Tests for PipelineExecutor  step sequencing, branching, error handling,
step timing, completed_at tracking, and execution timeout enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule
from backend.services.pipeline_executor import PipelineExecutor
from backend.steps.base import StepResult, TriggerContext


def _make_rule(db, name="Test Rule", **kwargs):
    rule = Rule(name=name, enabled=True, trigger_type="sensor_event", **kwargs)
    db.add(rule)
    db.flush()
    return rule


def _make_step(db, rule, order, step_type="notification", config=None, enabled=True):
    step = PipelineStep(
        rule_id=rule.id,
        order=order,
        step_type=step_type,
        config_json=config or {},
        enabled=enabled,
    )
    db.add(step)
    db.flush()
    return step


def _make_executor(db_factory):
    """Build a PipelineExecutor with all optional services mocked out."""
    executor = PipelineExecutor(db_session_factory=db_factory)
    return executor


def _make_trigger():
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id="cam1",
        room_name="Living Room",
        media_paths=[],
    )


class TestPipelineExecutorSequencing:
    async def test_empty_pipeline_completes_immediately(self, db_session, db_factory):
        rule = _make_rule(db_session)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(executor, "_execute_step", new_callable=AsyncMock) as mock_step:
            result = await executor.execute(rule, trigger, db_session)

        mock_step.assert_not_awaited()
        assert result.status == "completed"

    async def test_steps_executed_in_order(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        _make_step(db_session, rule, order=3, step_type="step_c")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()
        execution_order = []

        async def mock_execute(step, execution, pipeline_data, trigger):
            execution_order.append(step.step_type)
            return StepResult(success=True)

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            await executor.execute(rule, trigger, db_session)

        assert execution_order == ["step_a", "step_b", "step_c"]

    async def test_disabled_steps_skipped(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b", enabled=False)
        _make_step(db_session, rule, order=3, step_type="step_c")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()
        executed = []

        async def mock_execute(step, execution, pipeline_data, trigger):
            executed.append(step.step_type)
            return StepResult(success=True)

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            await executor.execute(rule, trigger, db_session)

        assert "step_b" not in executed
        assert executed == ["step_a", "step_c"]

    async def test_should_continue_false_stops_pipeline(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()
        executed = []

        async def mock_execute(step, execution, pipeline_data, trigger):
            executed.append(step.step_type)
            return StepResult(success=True, should_continue=False)

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        assert executed == ["step_a"]
        assert result.status == "completed"

    async def test_pipeline_data_accumulates_across_steps(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()
        seen_data = []

        async def mock_execute(step, execution, pipeline_data, trigger):
            seen_data.append(dict(pipeline_data))
            return StepResult(success=True, data={"from_" + step.step_type: True})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            await executor.execute(rule, trigger, db_session)

        # Step B should see data produced by step A
        assert "from_step_a" in seen_data[1]


class TestPipelineExecutorBranching:
    async def test_branch_target_not_found_logs_warning(self, db_session, db_factory):
        """When a condition step targets a non-existent step, execution should
        stop and a warning should be logged (not silently succeed)."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="condition")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            # Return a branch to a non-existent step ID
            return StepResult(success=True, next_step_id=99999)

        # Structlog doesn't propagate to Python logging so we patch the module logger.
        import backend.services.pipeline_executor as pe_module

        with patch.object(pe_module, "logger") as mock_logger, patch.object(executor, "_execute_step", side_effect=mock_execute):
                result = await executor.execute(rule, trigger, db_session)

        assert result.status == "completed"
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args
        assert "branch_target_not_found" in call_kwargs[0][0]

    async def test_valid_branch_skips_linear_sequence(self, db_session, db_factory):
        """A condition branching to step C should skip step B."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="condition")
        _make_step(db_session, rule, order=2, step_type="step_b")
        step_c = _make_step(db_session, rule, order=3, step_type="step_c")
        db_session.commit()

        # Reload to get IDs
        db_session.refresh(step_c)

        executor = _make_executor(db_factory)
        trigger = _make_trigger()
        executed = []

        async def mock_execute(step, execution, pipeline_data, trigger):
            executed.append(step.step_type)
            if step.step_type == "condition":
                return StepResult(success=True, next_step_id=step_c.id)
            return StepResult(success=True)

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            await executor.execute(rule, trigger, db_session)

        assert "step_b" not in executed
        assert "step_c" in executed


class TestPipelineExecutorErrors:
    async def test_step_exception_marks_execution_failed(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="bad_step")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def boom(step, execution, pipeline_data, trigger):
            raise RuntimeError("step exploded")

        with patch.object(executor, "_execute_step", side_effect=boom):
            result = await executor.execute(rule, trigger, db_session)

        assert result.status == "failed"
        assert "step exploded" in (result.error or "")

    async def test_unknown_step_type_returns_false_and_stops(self, db_session, db_factory):
        """An unregistered step type should not cause an unhandled exception;
        execution should stop gracefully."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="definitely_not_registered")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        # _execute_step dispatches to StepRegistry; unknown type returns StepResult(success=False)
        result = await executor.execute(rule, trigger, db_session)

        # Pipeline completes but with early exit (should_continue=False from unknown handler)
        assert result.status == "completed"


class TestPipelineExecutorStepTiming:
    """_step_timings and _pipeline timestamps are written into pipeline_data_json."""

    async def test_step_timing_recorded_for_each_step(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True)

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        timings = result.pipeline_data_json.get("_step_timings", [])
        assert len(timings) == 2
        types = [t["step_type"] for t in timings]
        assert types == ["step_a", "step_b"]

    async def test_step_timing_fields_present(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock,
            return_value=StepResult(success=True)
        ):
            result = await executor.execute(rule, trigger, db_session)

        entry = result.pipeline_data_json["_step_timings"][0]
        for field in ("step_id", "step_type", "started_at", "completed_at", "elapsed_seconds", "success"):
            assert field in entry, f"Missing field: {field}"
        assert entry["success"] is True
        assert entry["elapsed_seconds"] >= 0

    async def test_failed_step_timing_recorded_with_error(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="bad_step")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def boom(step, execution, pipeline_data, trigger):
            raise RuntimeError("kaboom")

        with patch.object(executor, "_execute_step", side_effect=boom):
            result = await executor.execute(rule, trigger, db_session)

        assert result.status == "failed"
        timings = result.pipeline_data_json.get("_step_timings", [])
        assert len(timings) == 1
        assert timings[0]["success"] is False
        assert "kaboom" in timings[0].get("error", "")

    async def test_pipeline_timing_block_written(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock,
            return_value=StepResult(success=True)
        ):
            result = await executor.execute(rule, trigger, db_session)

        pipeline_block = result.pipeline_data_json.get("_pipeline", {})
        assert "started_at" in pipeline_block
        assert "completed_at" in pipeline_block
        assert pipeline_block["completed_at"] is not None

    async def test_empty_pipeline_has_pipeline_timing(self, db_session, db_factory):
        rule = _make_rule(db_session)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()
        result = await executor.execute(rule, trigger, db_session)

        assert result.status == "completed"
        pipeline_block = result.pipeline_data_json.get("_pipeline", {})
        assert pipeline_block.get("completed_at") is not None


class TestPipelineExecutorCompletedAt:
    """WorkflowExecution.completed_at is set on all terminal paths."""

    async def test_completed_at_set_on_success(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock,
            return_value=StepResult(success=True)
        ):
            result = await executor.execute(rule, trigger, db_session)

        assert result.completed_at is not None

    async def test_completed_at_set_on_failure(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def boom(*args, **kwargs):
            raise RuntimeError("oops")

        with patch.object(executor, "_execute_step", side_effect=boom):
            result = await executor.execute(rule, trigger, db_session)

        assert result.status == "failed"
        assert result.completed_at is not None

    async def test_completed_at_set_on_early_exit(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock,
            return_value=StepResult(success=True, should_continue=False)
        ):
            result = await executor.execute(rule, trigger, db_session)

        assert result.status == "completed"
        assert result.completed_at is not None

    async def test_completed_at_set_for_empty_pipeline(self, db_session, db_factory):
        rule = _make_rule(db_session)
        db_session.commit()

        executor = _make_executor(db_factory)
        result = await executor.execute(rule, _make_trigger(), db_session)

        assert result.completed_at is not None


class TestPipelineExecutorTimeout:
    """Execution timeout is enforced via asyncio.wait_for."""

    async def test_timeout_marks_execution_failed(self, db_session, db_factory):
        """When asyncio.wait_for fires, the execution is marked failed."""
        rule = _make_rule(db_session, execution_timeout_minutes=5)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def immediate_timeout(coro, *, timeout):
            # Discard the coroutine cleanly and raise TimeoutError
            coro.close()
            raise TimeoutError()

        with patch("backend.services.pipeline_executor.asyncio.wait_for", new=immediate_timeout):
            result = await executor.execute(rule, trigger, db_session)

        assert result.status == "failed"
        assert "timed out" in (result.error or "").lower()
        assert "5 minute" in (result.error or "")

    async def test_timeout_sets_completed_at(self, db_session, db_factory):
        rule = _make_rule(db_session, execution_timeout_minutes=5)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def immediate_timeout(coro, *, timeout):
            coro.close()
            raise TimeoutError()

        with patch("backend.services.pipeline_executor.asyncio.wait_for", new=immediate_timeout):
            result = await executor.execute(rule, trigger, db_session)

        assert result.completed_at is not None

    async def test_no_timeout_when_zero(self, db_session, db_factory):
        """execution_timeout_minutes=0 passes None to wait_for (no limit)."""
        rule = _make_rule(db_session, execution_timeout_minutes=0)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        captured_timeout = []

        async def capturing_wait_for(coro, *, timeout):
            captured_timeout.append(timeout)
            return await coro

        with patch("backend.services.pipeline_executor.asyncio.wait_for", new=capturing_wait_for), \
             patch.object(executor, "_execute_step", new_callable=AsyncMock,
                          return_value=StepResult(success=True)):
            result = await executor.execute(rule, trigger, db_session)

        assert captured_timeout == [None]
        assert result.status == "completed"

    async def test_timeout_error_message_uses_singular_for_one_minute(self, db_session, db_factory):
        rule = _make_rule(db_session, execution_timeout_minutes=1)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)

        async def immediate_timeout(coro, *, timeout):
            coro.close()
            raise TimeoutError()

        with patch("backend.services.pipeline_executor.asyncio.wait_for", new=immediate_timeout):
            result = await executor.execute(rule, _make_trigger(), db_session)

        assert "1 minute" in result.error
        assert "minutes" not in result.error
