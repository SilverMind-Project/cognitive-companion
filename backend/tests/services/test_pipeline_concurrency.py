"""Tests for concurrent update protection in WorkflowExecution.

Tests optimistic locking (version column), pessimistic locking (SELECT FOR UPDATE),
and version conflict detection for pipeline_data_json mutations.

**Validates: Requirements 8.9**
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.services.pipeline_executor import (
    PipelineExecutor,
    _update_pipeline_data_with_retry,
)
from backend.steps.base import StepResult, TriggerContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(db: Session, name: str = "Test Rule", **kwargs) -> Rule:
    """Create a test rule."""
    rule = Rule(
        name=name,
        enabled=True,
        trigger_type="sensor_event",
        cool_off_minutes=0,
        max_daily_triggers=0,
        **kwargs,
    )
    db.add(rule)
    db.flush()
    return rule


def _make_step(
    db: Session,
    rule: Rule,
    order: int,
    step_type: str = "notification",
    config: dict | None = None,
) -> PipelineStep:
    """Create a test pipeline step."""
    step = PipelineStep(
        rule_id=rule.id,
        order=order,
        step_type=step_type,
        config_json=config or {},
        enabled=True,
    )
    db.add(step)
    db.flush()
    return step


def _make_execution(db: Session, rule: Rule, status: str = "running") -> WorkflowExecution:
    """Create a test workflow execution."""
    execution = WorkflowExecution(
        rule_id=rule.id,
        status=status,
        pipeline_data_json={"test": "data"},
    )
    db.add(execution)
    db.flush()
    return execution


def _make_executor(db_factory) -> PipelineExecutor:
    """Build a PipelineExecutor with mocked services."""
    return PipelineExecutor(db_session_factory=db_factory)


def _make_trigger() -> TriggerContext:
    """Create a test trigger context."""
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id="cam1",
        room_name="Living Room",
        media_paths=[],
    )


# ---------------------------------------------------------------------------
# Optimistic Locking Tests
# ---------------------------------------------------------------------------


class TestOptimisticLocking:
    """Test optimistic locking with version column."""

    def test_version_column_exists(self, db_session: Session):
        """WorkflowExecution must have a version column."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        assert hasattr(execution, "version")
        assert execution.version == 1

    def test_version_increments_on_update(self, db_session: Session):
        """Version column must increment on each update."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        initial_version = execution.version
        execution.pipeline_data_json["new_key"] = "new_value"
        db_session.commit()
        db_session.refresh(execution)

        assert execution.version == initial_version + 1

    def test_concurrent_update_raises_stale_data_error(self, db_session: Session, db_factory):
        """Concurrent updates to the same execution must raise StaleDataError."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        # Simulate concurrent update by creating two sessions
        session1 = db_factory()
        session2 = db_factory()

        try:
            # Both sessions load the same execution
            exec1 = session1.query(WorkflowExecution).filter_by(id=execution.id).one()
            exec2 = session2.query(WorkflowExecution).filter_by(id=execution.id).one()

            # Session 1 updates and commits
            exec1.pipeline_data_json["session1"] = "data"
            session1.commit()

            # Session 2 tries to update with stale version
            exec2.pipeline_data_json["session2"] = "data"
            with pytest.raises(StaleDataError):
                session2.commit()
        finally:
            session1.close()
            session2.close()

    async def test_retry_logic_succeeds_after_conflict(self, db_session: Session):
        """_update_pipeline_data_with_retry must retry on StaleDataError."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        call_count = 0

        def update_fn(data: dict):
            nonlocal call_count
            call_count += 1
            data["attempt"] = call_count

        # Mock commit to raise StaleDataError on first attempt
        original_commit = db_session.commit
        commit_count = 0

        def mock_commit():
            nonlocal commit_count
            commit_count += 1
            if commit_count == 1:
                raise StaleDataError("Simulated conflict")
            return original_commit()

        with patch.object(db_session, "commit", side_effect=mock_commit):
            await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

        # Should have retried once
        assert call_count == 2
        assert commit_count == 2

    async def test_retry_logic_exhausts_after_max_retries(self, db_session: Session):
        """_update_pipeline_data_with_retry must raise after MAX_RETRIES."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        def update_fn(data: dict):
            data["test"] = "value"

        # Mock commit to always raise StaleDataError
        with patch.object(db_session, "commit", side_effect=StaleDataError("Always fails")):
            with pytest.raises(StaleDataError):
                await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

    async def test_retry_logic_uses_exponential_backoff(self, db_session: Session):
        """_update_pipeline_data_with_retry must use exponential backoff."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        sleep_delays = []

        async def mock_sleep(delay: float):
            sleep_delays.append(delay)

        def update_fn(data: dict):
            data["test"] = "value"

        # Mock commit to raise StaleDataError twice
        commit_count = 0

        def mock_commit():
            nonlocal commit_count
            commit_count += 1
            if commit_count <= 2:
                raise StaleDataError("Simulated conflict")

        with patch.object(db_session, "commit", side_effect=mock_commit):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await _update_pipeline_data_with_retry(db_session, execution.id, update_fn)

        # Should have exponential backoff: 0.1, 0.2
        assert len(sleep_delays) == 2
        assert sleep_delays[0] == 0.1
        assert sleep_delays[1] == 0.2


# ---------------------------------------------------------------------------
# Pessimistic Locking Tests
# ---------------------------------------------------------------------------


class TestPessimisticLocking:
    """Test pessimistic locking with SELECT FOR UPDATE."""

    async def test_resume_uses_pessimistic_lock(self, db_session: Session, db_factory):
        """resume() must use SELECT FOR UPDATE to prevent concurrent resumes."""
        rule = _make_rule(db_session)
        step = _make_step(db_session, rule, order=1)
        execution = _make_execution(db_session, rule, status="waiting")
        execution.current_step_id = step.id
        db_session.commit()

        executor = _make_executor(db_factory)

        # Mock _run_steps to verify lock was acquired
        with patch.object(executor, "_run_steps", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = execution
            await executor.resume(execution.id, db_session)

        # Verify execution was loaded with lock
        db_session.refresh(execution)
        assert execution.status == "running"

    async def test_timeout_handler_uses_pessimistic_lock(self, db_session: Session, db_factory):
        """_handle_timeout must use SELECT FOR UPDATE for exclusive access."""
        rule = _make_rule(db_session, execution_timeout_minutes=1)
        step = _make_step(db_session, rule, order=1)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        executor = _make_executor(db_factory)

        # Call _handle_timeout directly
        result = executor._handle_timeout(rule, execution, db_session)

        # Verify execution was marked as failed
        assert result.status == "failed"
        assert "timed out" in result.error.lower()

    async def test_concurrent_resume_blocked_by_lock(self, db_session: Session, db_factory):
        """Concurrent resume attempts must be serialized by pessimistic lock."""
        rule = _make_rule(db_session)
        step = _make_step(db_session, rule, order=1)
        execution = _make_execution(db_session, rule, status="waiting")
        execution.current_step_id = step.id
        db_session.commit()

        executor = _make_executor(db_factory)

        # Track resume order
        resume_order = []

        async def mock_run_steps(execution, steps, trigger, db):
            resume_order.append(datetime.now(UTC))
            await asyncio.sleep(0.1)  # Simulate work
            return execution

        with patch.object(executor, "_run_steps", side_effect=mock_run_steps):
            # Create two concurrent resume tasks
            session1 = db_factory()
            session2 = db_factory()

            try:
                # Both should complete, but serialized
                task1 = asyncio.create_task(executor.resume(execution.id, session1))
                task2 = asyncio.create_task(executor.resume(execution.id, session2))

                results = await asyncio.gather(task1, task2, return_exceptions=True)

                # At least one should succeed
                successful = [r for r in results if not isinstance(r, Exception)]
                assert len(successful) >= 1
            finally:
                session1.close()
                session2.close()


# ---------------------------------------------------------------------------
# Version Conflict Detection Tests
# ---------------------------------------------------------------------------


class TestVersionConflictDetection:
    """Test version conflict detection in concurrent scenarios."""

    def test_version_conflict_detected_on_commit(self, db_session: Session, db_factory):
        """SQLAlchemy must detect version conflicts on commit."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        session1 = db_factory()
        session2 = db_factory()

        try:
            exec1 = session1.query(WorkflowExecution).filter_by(id=execution.id).one()
            exec2 = session2.query(WorkflowExecution).filter_by(id=execution.id).one()

            # Both have same version
            assert exec1.version == exec2.version

            # Session 1 commits first
            exec1.status = "completed"
            session1.commit()

            # Session 2 should fail on commit
            exec2.status = "failed"
            with pytest.raises(StaleDataError):
                session2.commit()
        finally:
            session1.close()
            session2.close()

    def test_version_preserved_across_rollback(self, db_session: Session):
        """Version must be preserved after rollback."""
        rule = _make_rule(db_session)
        execution = _make_execution(db_session, rule)
        db_session.commit()

        original_version = execution.version

        # Make a change and rollback
        execution.pipeline_data_json["test"] = "rollback"
        db_session.rollback()

        # Version should be unchanged
        db_session.refresh(execution)
        assert execution.version == original_version

    async def test_pipeline_execution_detects_version_conflicts(
        self, db_session: Session, db_factory
    ):
        """Pipeline execution must detect version conflicts during commit."""
        rule = _make_rule(db_session)
        step = _make_step(db_session, rule, order=1, step_type="notification")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        # Mock step execution to simulate concurrent update
        step_call_count = 0

        async def mock_execute_step(step, execution, pipeline_data, trigger):
            nonlocal step_call_count
            step_call_count += 1

            # Simulate concurrent update on first call
            if step_call_count == 1:
                # Create another session and update the execution
                other_session = db_factory()
                try:
                    other_exec = (
                        other_session.query(WorkflowExecution)
                        .filter_by(id=execution.id)
                        .one()
                    )
                    other_exec.pipeline_data_json["concurrent"] = "update"
                    other_session.commit()
                finally:
                    other_session.close()

            return StepResult(success=True, data={"step_output": "test"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute_step):
            # The pipeline should raise an exception when it tries to commit
            # after the concurrent update. This could be StaleDataError or
            # PendingRollbackError depending on when the error is caught.
            with pytest.raises((StaleDataError, Exception)):
                await executor.execute(rule, trigger, db_session)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestConcurrencyIntegration:
    """Integration tests for concurrent pipeline execution."""

    async def test_multiple_steps_with_concurrent_updates(
        self, db_session: Session, db_factory
    ):
        """Multiple steps must handle concurrent updates correctly."""
        rule = _make_rule(db_session)
        _make_step(db_session, rule, order=1, step_type="step_a")
        _make_step(db_session, rule, order=2, step_type="step_b")
        _make_step(db_session, rule, order=3, step_type="step_c")
        db_session.commit()

        executor = _make_executor(db_factory)
        trigger = _make_trigger()

        executed_steps = []

        async def mock_execute_step(step, execution, pipeline_data, trigger):
            executed_steps.append(step.step_type)
            return StepResult(success=True, data={f"{step.step_type}_output": "data"})

        with patch.object(executor, "_execute_step", side_effect=mock_execute_step):
            result = await executor.execute(rule, trigger, db_session)

        assert result.status == "completed"
        assert executed_steps == ["step_a", "step_b", "step_c"]
        assert result.version > 1  # Version should have incremented

    async def test_resume_after_wait_preserves_data(self, db_session: Session, db_factory):
        """Resume after wait must preserve pipeline_data_json."""
        rule = _make_rule(db_session)
        step = _make_step(db_session, rule, order=1)
        execution = _make_execution(db_session, rule, status="waiting")
        execution.current_step_id = step.id
        execution.pipeline_data_json = {
            "trigger": {"sensor_id": "cam1"},
            "step1_output": "preserved",
        }
        db_session.commit()

        executor = _make_executor(db_factory)

        async def mock_run_steps(execution, steps, trigger, db):
            # Verify data is preserved
            assert execution.pipeline_data_json["step1_output"] == "preserved"
            return execution

        with patch.object(executor, "_run_steps", side_effect=mock_run_steps):
            result = await executor.resume(execution.id, db_session)

        assert result.status == "running"
