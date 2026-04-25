"""Tests for PipelineExecutor  step sequencing, branching, error handling,
step timing, completed_at tracking, and execution timeout enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.models.event import EventLog
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

        with (
            patch.object(pe_module, "logger") as mock_logger,
            patch.object(executor, "_execute_step", side_effect=mock_execute),
        ):
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

    async def test_unknown_step_type_routes_to_failed(self, db_session, db_factory):
        """An unregistered step type must surface as a failure, not a silent
        ``completed``. ``StepRegistry.get`` returns ``None`` so the executor
        synthesises ``StepResult(success=False, should_continue=False)`` and
        the early-exit branch routes that to ``status=failed`` on both the
        execution and the event log.
        """
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="definitely_not_registered")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        result = await executor.execute(rule, trigger, db_session)

        assert result.status == "failed"
        event_log = db_session.query(EventLog).filter(EventLog.id == result.event_log_id).first()
        assert event_log is not None
        assert event_log.status == "failed"


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
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
        ):
            result = await executor.execute(rule, trigger, db_session)

        entry = result.pipeline_data_json["_step_timings"][0]
        for field in (
            "step_id",
            "step_type",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "success",
        ):
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
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
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
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
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
            executor,
            "_execute_step",
            new_callable=AsyncMock,
            return_value=StepResult(success=True, should_continue=False),
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

        with (
            patch("backend.services.pipeline_executor.asyncio.wait_for", new=capturing_wait_for),
            patch.object(
                executor,
                "_execute_step",
                new_callable=AsyncMock,
                return_value=StepResult(success=True),
            ),
        ):
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


class TestPipelineExecutorPersistence:
    """Regression suite for SQLAlchemy JSON change detection.

    The session factory runs with ``expire_on_commit=False``, so after a
    commit the ORM keeps its existing Python references rather than reloading
    from the database. Before the MutableDict fix, ``_run_steps`` passed a
    shallow copy of ``pipeline_data_json`` around and reassigned the same
    reference on every iteration. SQLAlchemy's equality-based dirty check saw
    no change on iterations 2+ and silently dropped every mutation from the
    second step onwards, while the scalar ``status`` and ``completed_at``
    columns still flushed. The row ended up marked ``completed`` with a
    ``pipeline_data_json`` frozen at the end of the first step.

    These tests drive the executor across two or more steps and then read the
    row back to verify every write was persisted. ``db_session.refresh``
    bypasses any in-memory attribute state so a missing flush surfaces as a
    failed assertion instead of a false pass.
    """

    async def test_multi_step_pipeline_data_persists_across_commits(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        _make_step(db_session, rule, order=3, step_type="step_c")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={f"from_{step.step_type}": True})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            execution = await executor.execute(rule, trigger, db_session)

        # Force a round-trip through the database so stale in-memory state
        # cannot mask a missing flush.
        db_session.refresh(execution)
        data = execution.pipeline_data_json

        assert data["from_step_a"] is True
        assert data["from_step_b"] is True
        assert data["from_step_c"] is True

        timings = data.get("_step_timings", [])
        assert [t["step_type"] for t in timings] == ["step_a", "step_b", "step_c"]
        assert all(t["success"] is True for t in timings)

    async def test_pipeline_completed_at_persists_after_reload(self, db_session, db_factory):
        """Nested mutation of ``_pipeline.completed_at`` must land on disk.

        ``MutableDict`` only tracks top-level ``__setitem__`` / ``update``
        calls; ``pipeline_data['_pipeline']['completed_at'] = ...`` is a
        nested write, so the executor must call ``flag_modified`` for the
        change to survive ``db.refresh``.
        """
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor,
            "_execute_step",
            new_callable=AsyncMock,
            return_value=StepResult(success=True),
        ):
            execution = await executor.execute(rule, trigger, db_session)

        db_session.refresh(execution)
        pipeline_block = execution.pipeline_data_json.get("_pipeline", {})
        assert pipeline_block.get("completed_at") is not None
        # Must be an ISO timestamp, not the null placeholder from execute().
        assert pipeline_block["completed_at"] != ""
        datetime_like = pipeline_block["completed_at"]
        assert "T" in datetime_like

    async def test_event_log_snapshot_contains_final_pipeline_data(self, db_session, db_factory):
        """The event log snapshot written on completion must include every
        step's output, not just the first step's. Regression for the drift
        between ``WorkflowExecution.pipeline_data_json`` and
        ``EventLog.pipeline_data_json`` when iterations 2+ were lost."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={f"from_{step.step_type}": True})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            execution = await executor.execute(rule, trigger, db_session)

        event_log = db_session.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
        assert event_log is not None
        db_session.refresh(event_log)

        payload = event_log.pipeline_data_json or {}
        assert payload.get("from_step_a") is True
        assert payload.get("from_step_b") is True


class TestPipelineExecutorEarlyExit:
    """Early-exit routing based on ``StepResult.success``.

    A step can request ``should_continue=False`` for two unrelated reasons:
    it intentionally skipped (``success=True``) or it errored out
    (``success=False``). The executor must distinguish these so rate-limit,
    cool-off, and UI status tracking stay accurate.
    """

    async def test_success_skip_marks_event_log_ignored(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor,
            "_execute_step",
            new_callable=AsyncMock,
            return_value=StepResult(
                success=True,
                should_continue=False,
                data={"skip_reason": "target_person_not_detected"},
            ),
        ):
            execution = await executor.execute(rule, trigger, db_session)

        assert execution.status == "completed"
        event_log = db_session.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
        assert event_log is not None
        assert event_log.status == "ignored"
        # The skip_reason must be preserved in the event log snapshot so the
        # UI can explain *why* an event was ignored without reading live state.
        assert (event_log.pipeline_data_json or {}).get("skip_reason") == (
            "target_person_not_detected"
        )

    async def test_failure_early_exit_marks_execution_and_event_log_failed(
        self, db_session, db_factory
    ):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor,
            "_execute_step",
            new_callable=AsyncMock,
            return_value=StepResult(success=False, should_continue=False),
        ):
            execution = await executor.execute(rule, trigger, db_session)

        assert execution.status == "failed"
        event_log = db_session.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
        assert event_log is not None
        assert event_log.status == "failed"

    async def test_early_exit_sets_completed_at_on_execution(self, db_session, db_factory):
        """Both branches of the early exit (skip vs failure) must stamp
        ``completed_at`` so the workflow isn't left in limbo."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)

        with patch.object(
            executor,
            "_execute_step",
            new_callable=AsyncMock,
            return_value=StepResult(success=False, should_continue=False),
        ):
            execution = await executor.execute(rule, _make_trigger(), db_session)

        db_session.refresh(execution)
        assert execution.completed_at is not None
        block = execution.pipeline_data_json.get("_pipeline", {})
        assert block.get("completed_at") is not None

    async def test_skip_reason_logged_on_early_exit(self, db_session, db_factory):
        """Operators need to see *why* a pipeline bailed early without
        digging into the JSON payload. The ``pipeline_early_exit`` log line
        should carry both the routed event log status and the skip_reason.
        """
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        import backend.services.pipeline_executor as pe_module

        with (
            patch.object(pe_module, "logger") as mock_logger,
            patch.object(
                executor,
                "_execute_step",
                new_callable=AsyncMock,
                return_value=StepResult(
                    success=True,
                    should_continue=False,
                    data={"skip_reason": "target_person_not_detected"},
                ),
            ),
        ):
            await executor.execute(rule, trigger, db_session)

        early_exit_calls = [
            call
            for call in mock_logger.info.call_args_list
            if call.args and call.args[0] == "pipeline_early_exit"
        ]
        assert len(early_exit_calls) == 1
        kwargs = early_exit_calls[0].kwargs
        assert kwargs.get("skip_reason") == "target_person_not_detected"
        assert kwargs.get("event_log_status") == "ignored"

    async def test_no_skip_reason_logs_none(self, db_session, db_factory):
        """When a step requests early exit without providing ``skip_reason``,
        the log line should still fire but with ``skip_reason=None``."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        import backend.services.pipeline_executor as pe_module

        with (
            patch.object(pe_module, "logger") as mock_logger,
            patch.object(
                executor,
                "_execute_step",
                new_callable=AsyncMock,
                return_value=StepResult(success=True, should_continue=False),
            ),
        ):
            await executor.execute(rule, trigger, db_session)

        early_exit_calls = [
            call
            for call in mock_logger.info.call_args_list
            if call.args and call.args[0] == "pipeline_early_exit"
        ]
        assert len(early_exit_calls) == 1
        assert early_exit_calls[0].kwargs.get("skip_reason") is None


class TestOptimisticLockingRetry:
    """Tests for _update_pipeline_data_with_retry function."""

    async def test_successful_update_on_first_attempt(self, db_session, db_factory):
        """When no conflict occurs, update succeeds on first attempt."""
        from backend.services.pipeline_executor import _update_pipeline_data_with_retry

        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
        ):
            execution = await executor.execute(rule, trigger, db_session)

        # Update pipeline data using retry logic
        def update_fn(data):
            data["test_key"] = "test_value"

        await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

        db_session.refresh(execution)
        assert execution.pipeline_data_json["test_key"] == "test_value"

    async def test_retry_on_stale_data_error(self, db_session, db_factory):
        """When StaleDataError occurs, function retries with exponential backoff."""
        from sqlalchemy.orm.exc import StaleDataError

        from backend.services.pipeline_executor import _update_pipeline_data_with_retry

        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
        ):
            execution = await executor.execute(rule, trigger, db_session)

        # Simulate StaleDataError on first attempt, success on second
        attempt_count = [0]

        original_commit = db_session.commit

        def mock_commit():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise StaleDataError("Version mismatch")
            return original_commit()

        def update_fn(data):
            data["retry_test"] = f"attempt_{attempt_count[0]}"

        with patch.object(db_session, "commit", side_effect=mock_commit):
            await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

        # Should have retried once
        assert attempt_count[0] == 2

    async def test_exhausted_retries_raises_error(self, db_session, db_factory):
        """When all retries are exhausted, StaleDataError is raised."""
        import pytest
        from sqlalchemy.orm.exc import StaleDataError

        from backend.services.pipeline_executor import _update_pipeline_data_with_retry

        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
        ):
            execution = await executor.execute(rule, trigger, db_session)

        def update_fn(data):
            data["will_fail"] = True

        # Mock commit to always raise StaleDataError
        with (
            patch.object(db_session, "commit", side_effect=StaleDataError("Always fails")),
            pytest.raises(StaleDataError),
        ):
            await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

    async def test_lock_conflict_logging(self, db_session, db_factory):
        """Lock conflicts are logged with appropriate warnings."""
        from sqlalchemy.orm.exc import StaleDataError

        import backend.services.pipeline_executor as pe_module
        from backend.services.pipeline_executor import _update_pipeline_data_with_retry

        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1)
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        with patch.object(
            executor, "_execute_step", new_callable=AsyncMock, return_value=StepResult(success=True)
        ):
            execution = await executor.execute(rule, trigger, db_session)

        attempt_count = [0]
        original_commit = db_session.commit

        def mock_commit():
            attempt_count[0] += 1
            if attempt_count[0] == 1:
                raise StaleDataError("Version mismatch")
            return original_commit()

        def update_fn(data):
            data["logging_test"] = True

        with (
            patch.object(pe_module, "logger") as mock_logger,
            patch.object(db_session, "commit", side_effect=mock_commit),
        ):
            await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

        # Verify warning was logged
        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if call.args and call.args[0] == "optimistic_lock_conflict"
        ]
        assert len(warning_calls) == 1
        kwargs = warning_calls[0].kwargs
        assert kwargs.get("execution_id") == execution.id
        assert kwargs.get("attempt") == 1


class TestCanonicalStepNamespace:
    """Canonical steps.by_id namespace is written and survives persistence."""

    async def test_canonical_namespace_written_after_step(self, db_session, db_factory):
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="llm_call")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={"vision_response": "hello"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        db_session.refresh(result)
        data = result.pipeline_data_json
        assert "steps" in data
        by_id = data["steps"]["by_id"]
        assert len(by_id) == 1
        entry = next(iter(by_id.values()))
        assert entry["step_type"] == "llm_call"
        assert entry["outputs"]["vision_response"] == "hello"

    async def test_two_same_type_steps_both_in_canonical_namespace(self, db_session, db_factory):
        """Two llm_call steps with the same output_key must both survive under steps.by_id."""
        rule = _make_rule(db_session)
        step_a = _make_step(db_session, rule, order=1, step_type="llm_call")
        step_b = _make_step(db_session, rule, order=2, step_type="llm_call")
        db_session.commit()
        db_session.refresh(step_a)
        db_session.refresh(step_b)

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={"llm_response": f"from_{step.order}"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        db_session.refresh(result)
        data = result.pipeline_data_json
        by_id = data["steps"]["by_id"]
        assert len(by_id) == 2

        id_a = str(step_a.id)
        id_b = str(step_b.id)
        assert by_id[id_a]["outputs"]["llm_response"] == "from_1"
        assert by_id[id_b]["outputs"]["llm_response"] == "from_2"

    async def test_legacy_top_level_alias_still_present_for_single_step(
        self, db_session, db_factory
    ):
        """Legacy top-level alias must still be written for backward compatibility."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="llm_call")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={"vision_response": "result"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        db_session.refresh(result)
        assert result.pipeline_data_json.get("vision_response") == "result"

    async def test_label_slug_alias_written_to_by_label(self, db_session, db_factory):
        rule = _make_rule(db_session)
        step = _make_step(db_session, rule, order=1, step_type="llm_call")
        step.label = "Vision Analysis"
        db_session.commit()
        db_session.refresh(step)

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(s, execution, pipeline_data, trigger):
            return StepResult(success=True, data={"vision_response": "ok"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        db_session.refresh(result)
        by_label = result.pipeline_data_json["steps"]["by_label"]
        assert "vision_analysis" in by_label
        assert by_label["vision_analysis"] == str(step.id)

    async def test_event_log_snapshot_contains_canonical_step_data(
        self, db_session, db_factory
    ):
        """Event log snapshot must include the canonical steps namespace."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="llm_call")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={"vision_response": "snapshot_test"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            execution = await executor.execute(rule, trigger, db_session)

        from backend.models.event import EventLog
        event_log = db_session.query(EventLog).filter(
            EventLog.id == execution.event_log_id
        ).first()
        assert event_log is not None
        db_session.refresh(event_log)

        payload = event_log.pipeline_data_json or {}
        assert "steps" in payload
        assert len(payload["steps"]["by_id"]) == 1

    async def test_alias_collision_logged_for_duplicate_output_keys(
        self, db_session, db_factory
    ):
        """When two steps write the same legacy key, a collision is recorded."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="llm_call")
        _make_step(db_session, rule, order=2, step_type="llm_call")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        async def mock_execute(step, execution, pipeline_data, trigger):
            return StepResult(success=True, data={"llm_response": f"step_{step.order}"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.execute(rule, trigger, db_session)

        db_session.refresh(result)
        data = result.pipeline_data_json
        # Last writer wins at top level
        assert data.get("llm_response") == "step_2"
        # Collision recorded
        collisions = data.get("_alias_collisions", [])
        assert len(collisions) == 1
        assert collisions[0]["key"] == "llm_response"

    async def test_exception_cleanup_after_stale_data_error(self, db_session, db_factory):
        """After a commit failure the except block must not raise PendingRollbackError."""
        from sqlalchemy.orm.exc import StaleDataError

        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="llm_call")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        commit_count = [0]
        original_commit = db_session.commit

        def patched_commit():
            commit_count[0] += 1
            # Fail on the step-data commit (3rd commit: event_log, execution, step)
            if commit_count[0] == 3:
                raise StaleDataError("simulated conflict")
            return original_commit()

        with patch.object(db_session, "commit", side_effect=patched_commit):
            result = await executor.execute(rule, trigger, db_session)

        # Must be failed, not an unhandled exception
        assert result.status == "failed"


class TestInteractivePromptResumeIntegration:
    """Executor merges interactive response during resume()."""

    async def test_resume_merges_response_into_pipeline_data(self, db_session, db_factory):
        """When an interactive_prompt step has a recorded response, resume() must
        merge it into pipeline_data before advancing to the next step."""
        from datetime import UTC, datetime

        from backend.models.interactive_response import InteractiveResponse
        from backend.models.pipeline import WorkflowExecution

        rule = _make_rule(db_session)
        prompt_step = _make_step(db_session, rule, order=1, step_type="interactive_prompt",
                                  config={"output_key": "interactive_response", "auto_escalate": False})
        next_step = _make_step(db_session, rule, order=2, step_type="notification")
        db_session.commit()
        db_session.refresh(prompt_step)
        db_session.refresh(next_step)

        # Create a waiting execution paused at the interactive_prompt step
        execution = WorkflowExecution(
            rule_id=rule.id,
            status="waiting",
            current_step_id=prompt_step.id,
            pipeline_data_json={
                "trigger": {"sensor_id": "cam1", "room_name": "Kitchen",
                            "media_paths": [], "media_type": "image"},
                "steps": {"by_id": {}, "by_label": {}, "sequence": []},
            },
        )
        db_session.add(execution)
        db_session.commit()
        db_session.refresh(execution)

        # Record a response
        response = InteractiveResponse(
            execution_id=execution.id,
            step_id=prompt_step.id,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response_json={"button_id": "escalate"},
        )
        db_session.add(response)
        db_session.commit()

        executor = _make_executor(db_factory)
        seen_data = []

        async def mock_execute(step, exec_, pipeline_data, trigger):
            seen_data.append(dict(pipeline_data))
            return StepResult(success=True)

        with patch.object(executor, "_execute_step", side_effect=mock_execute):
            result = await executor.resume(execution.id, db_session)

        assert result.status == "completed"
        # The notification step should have seen the merged response
        assert len(seen_data) == 1
        assert "interactive_response" in seen_data[0]
        assert seen_data[0]["interactive_response"]["action"] == "escalate"

    async def test_resume_stays_waiting_when_no_response(self, db_session, db_factory):
        """If no InteractiveResponse exists yet, resume() must keep the execution waiting."""
        from backend.models.pipeline import WorkflowExecution

        rule = _make_rule(db_session)
        prompt_step = _make_step(db_session, rule, order=1, step_type="interactive_prompt",
                                  config={"output_key": "interactive_response"})
        db_session.commit()
        db_session.refresh(prompt_step)

        execution = WorkflowExecution(
            rule_id=rule.id,
            status="waiting",
            current_step_id=prompt_step.id,
            pipeline_data_json={"trigger": {}, "steps": {"by_id": {}, "by_label": {}, "sequence": []}},
        )
        db_session.add(execution)
        db_session.commit()
        db_session.refresh(execution)

        executor = _make_executor(db_factory)

        with patch.object(executor, "_execute_step", new_callable=AsyncMock) as mock_step:
            result = await executor.resume(execution.id, db_session)

        # Must remain waiting -- no step should have been executed
        assert result.status == "waiting"
        mock_step.assert_not_awaited()
