"""Unit tests for InteractiveResponseService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from backend.models.interactive_response import InteractiveResponse
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.services.interactive_response import InteractiveResponseService


@dataclass
class FakeScheduler:
    """Fake scheduler for testing."""

    resume_calls: list[tuple[int, datetime]]
    remove_job_calls: list[str]

    @dataclass
    class FakeAPScheduler:
        """Fake APScheduler."""

        remove_job_calls: list[str]

        def remove_job(self, job_id: str) -> None:
            self.remove_job_calls.append(job_id)

    def __init__(self) -> None:
        self.resume_calls = []
        self.remove_job_calls = []
        self.apscheduler = self.FakeAPScheduler(remove_job_calls=self.remove_job_calls)

    def schedule_workflow_resume(self, execution_id: int, resume_at: datetime) -> None:
        self.resume_calls.append((execution_id, resume_at))


@pytest.fixture
def fake_scheduler() -> FakeScheduler:
    """Provide a fake scheduler for testing."""
    return FakeScheduler()


@pytest.fixture
def test_rule(db_factory) -> Rule:
    """Create a test rule for foreign key constraints."""
    db: Session = db_factory()
    try:
        rule = Rule(
            name="Test Rule",
            description="Test rule for interactive response tests",
            enabled=True,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule
    finally:
        db.close()


@pytest.fixture
def test_step(db_factory, test_rule: Rule) -> PipelineStep:
    """Create a test pipeline step for foreign key constraints."""
    db: Session = db_factory()
    try:
        step = PipelineStep(
            rule_id=test_rule.id,
            order=0,
            step_type="interactive_prompt",
            label="Test Interactive Prompt",
            config_json={},
        )
        db.add(step)
        db.commit()
        db.refresh(step)
        return step
    finally:
        db.close()


@pytest.fixture
def test_execution(db_factory, test_rule: Rule) -> WorkflowExecution:
    """Create a test workflow execution for foreign key constraints."""
    db: Session = db_factory()
    try:
        execution = WorkflowExecution(
            rule_id=test_rule.id,
            status="waiting",
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return execution
    finally:
        db.close()


@pytest.fixture
def service(db_factory, fake_scheduler: FakeScheduler) -> InteractiveResponseService:
    """Provide an InteractiveResponseService with test dependencies."""
    return InteractiveResponseService(
        db_factory=db_factory,
        scheduler=fake_scheduler,
    )


# ---------------------------------------------------------------------------
# record_response() - success cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_response_success(
    service: InteractiveResponseService,
    db_factory,
    fake_scheduler: FakeScheduler,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Happy path: response persisted and resume scheduled."""
    timestamp = datetime.now(UTC)
    raw_response = {"button_id": "escalate"}

    result = await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response=raw_response,
    )

    assert result is not None
    assert result.execution_id == test_execution.id
    assert result.step_id == test_step.id
    assert result.channel == "pwa_popup_text"
    assert result.action == "escalate"
    assert result.timestamp == timestamp
    assert result.raw_response_json == raw_response

    # Verify persisted to database
    db: Session = db_factory()
    try:
        persisted = (
            db.query(InteractiveResponse)
            .filter(
                InteractiveResponse.execution_id == test_execution.id,
                InteractiveResponse.step_id == test_step.id,
            )
            .first()
        )
        assert persisted is not None
        assert persisted.channel == "pwa_popup_text"
        assert persisted.action == "escalate"
    finally:
        db.close()

    # Verify resume scheduled
    assert len(fake_scheduler.resume_calls) == 1
    assert fake_scheduler.resume_calls[0][0] == test_execution.id


@pytest.mark.asyncio
async def test_record_response_voice_channel(
    service: InteractiveResponseService,
    db_factory,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Voice channel response recorded correctly."""
    timestamp = datetime.now(UTC)
    raw_response = {"needs_help": True, "user_statement": "I fell down"}

    result = await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_realtime_ai",
        action="escalate",
        timestamp=timestamp,
        raw_response=raw_response,
    )

    assert result is not None
    assert result.channel == "pwa_realtime_ai"
    assert result.raw_response_json == raw_response


@pytest.mark.asyncio
async def test_record_response_timeout_channel(
    service: InteractiveResponseService,
    db_factory,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Timeout response recorded correctly."""
    timestamp = datetime.now(UTC)
    raw_response = {"timeout_action": "dismiss"}

    result = await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="timeout",
        action="dismiss",
        timestamp=timestamp,
        raw_response=raw_response,
    )

    assert result is not None
    assert result.channel == "timeout"
    assert result.action == "dismiss"


# ---------------------------------------------------------------------------
# record_response() - duplicate handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_response_duplicate(
    service: InteractiveResponseService,
    db_factory,
    fake_scheduler: FakeScheduler,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Second response ignored, returns None."""
    timestamp = datetime.now(UTC)
    raw_response = {"button_id": "escalate"}

    # First response succeeds
    result1 = await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response=raw_response,
    )
    assert result1 is not None

    # Second response returns None (duplicate)
    result2 = await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_realtime_ai",
        action="dismiss",
        timestamp=timestamp,
        raw_response={"needs_help": False},
    )
    assert result2 is None

    # Verify only one record in database
    db: Session = db_factory()
    try:
        count = (
            db.query(InteractiveResponse)
            .filter(
                InteractiveResponse.execution_id == test_execution.id,
                InteractiveResponse.step_id == test_step.id,
            )
            .count()
        )
        assert count == 1

        # Verify first response is the one persisted
        persisted = (
            db.query(InteractiveResponse)
            .filter(
                InteractiveResponse.execution_id == test_execution.id,
                InteractiveResponse.step_id == test_step.id,
            )
            .first()
        )
        assert persisted.channel == "pwa_popup_text"
        assert persisted.action == "escalate"
    finally:
        db.close()

    # Verify resume only scheduled once
    assert len(fake_scheduler.resume_calls) == 1


# ---------------------------------------------------------------------------
# record_response() - validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_response_invalid_execution_id(
    service: InteractiveResponseService,
) -> None:
    """ValueError raised for invalid execution_id."""
    with pytest.raises(ValueError, match="execution_id must be a positive integer"):
        await service.record_response(
            execution_id=0,
            step_id=456,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response={},
        )

    with pytest.raises(ValueError, match="execution_id must be a positive integer"):
        await service.record_response(
            execution_id=-1,
            step_id=456,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response={},
        )


@pytest.mark.asyncio
async def test_record_response_invalid_step_id(
    service: InteractiveResponseService,
) -> None:
    """ValueError raised for invalid step_id."""
    with pytest.raises(ValueError, match="step_id must be a positive integer"):
        await service.record_response(
            execution_id=123,
            step_id=0,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response={},
        )


@pytest.mark.asyncio
async def test_record_response_invalid_channel(
    service: InteractiveResponseService,
) -> None:
    """ValueError raised for invalid channel."""
    with pytest.raises(ValueError, match="channel must be one of"):
        await service.record_response(
            execution_id=123,
            step_id=456,
            channel="invalid_channel",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response={},
        )


@pytest.mark.asyncio
async def test_record_response_invalid_action(
    service: InteractiveResponseService,
) -> None:
    """ValueError raised for invalid action."""
    with pytest.raises(ValueError, match="action must be one of"):
        await service.record_response(
            execution_id=123,
            step_id=456,
            channel="pwa_popup_text",
            action="invalid_action",
            timestamp=datetime.now(UTC),
            raw_response={},
        )


@pytest.mark.asyncio
async def test_record_response_invalid_timestamp(
    service: InteractiveResponseService,
) -> None:
    """ValueError raised for invalid timestamp."""
    with pytest.raises(ValueError, match="timestamp must be a datetime object"):
        await service.record_response(
            execution_id=123,
            step_id=456,
            channel="pwa_popup_text",
            action="escalate",
            timestamp="not a datetime",  # type: ignore
            raw_response={},
        )


@pytest.mark.asyncio
async def test_record_response_invalid_raw_response(
    service: InteractiveResponseService,
) -> None:
    """ValueError raised for invalid raw_response."""
    with pytest.raises(ValueError, match="raw_response must be a dict"):
        await service.record_response(
            execution_id=123,
            step_id=456,
            channel="pwa_popup_text",
            action="escalate",
            timestamp=datetime.now(UTC),
            raw_response="not a dict",  # type: ignore
        )


# ---------------------------------------------------------------------------
# get_response()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_response_found(
    service: InteractiveResponseService,
    db_factory,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Response retrieved by execution_id and step_id."""
    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response={"button_id": "escalate"},
    )

    response = service.get_response(execution_id=test_execution.id, step_id=test_step.id)
    assert response is not None
    assert response.execution_id == test_execution.id
    assert response.step_id == test_step.id
    assert response.channel == "pwa_popup_text"
    assert response.action == "escalate"


def test_get_response_not_found(service: InteractiveResponseService) -> None:
    """Returns None when no response exists."""
    response = service.get_response(execution_id=999, step_id=888)
    assert response is None


# ---------------------------------------------------------------------------
# check_response_exists()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_response_exists_true(
    service: InteractiveResponseService,
    db_factory,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Returns True when response exists."""
    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response={},
    )

    exists = service.check_response_exists(execution_id=test_execution.id, step_id=test_step.id)
    assert exists is True


def test_check_response_exists_false(service: InteractiveResponseService) -> None:
    """Returns False when no response exists."""
    exists = service.check_response_exists(execution_id=999, step_id=888)
    assert exists is False


# ---------------------------------------------------------------------------
# cancel_pending_response()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_pending_response(
    service: InteractiveResponseService,
    fake_scheduler: FakeScheduler,
) -> None:
    """Timeout task cancelled successfully."""
    await service.cancel_pending_response(execution_id=123, step_id=456)

    assert len(fake_scheduler.remove_job_calls) == 1
    assert fake_scheduler.remove_job_calls[0] == "interactive_timeout_123_456"


@pytest.mark.asyncio
async def test_cancel_pending_response_job_not_found(
    service: InteractiveResponseService,
    fake_scheduler: FakeScheduler,
) -> None:
    """Handles missing job gracefully (no exception)."""

    # Make remove_job raise an exception
    def raise_exception(job_id: str) -> None:
        raise Exception("Job not found")

    fake_scheduler.apscheduler.remove_job = raise_exception  # type: ignore

    # Should not raise exception
    await service.cancel_pending_response(execution_id=123, step_id=456)


# ---------------------------------------------------------------------------
# Ownership model: service does NOT write pipeline_data_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_response_does_not_write_pipeline_data(
    service: InteractiveResponseService,
    db_factory,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Service must NOT write to WorkflowExecution.pipeline_data_json.

    The executor is the sole writer of pipeline_data_json.
    """
    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response={"button_id": "escalate"},
    )

    db: Session = db_factory()
    try:
        execution = (
            db.query(WorkflowExecution).filter(WorkflowExecution.id == test_execution.id).first()
        )
        assert execution is not None
        pipeline_data = execution.pipeline_data_json
        # The service must not have written interactive_response into pipeline_data
        assert not pipeline_data or "interactive_response" not in (pipeline_data or {})
    finally:
        db.close()


@pytest.mark.asyncio
async def test_response_row_persisted_with_correct_fields(
    service: InteractiveResponseService,
    db_factory,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """InteractiveResponse row contains all fields needed for executor merge."""
    timestamp = datetime.now(UTC)
    raw_response = {"button_id": "escalate", "extra_data": "test"}

    result = await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response=raw_response,
    )

    assert result is not None
    assert result.channel == "pwa_popup_text"
    assert result.action == "escalate"
    assert result.raw_response_json == raw_response


@pytest.mark.asyncio
async def test_timeout_channel_does_not_cancel_timeout_job(
    service: InteractiveResponseService,
    db_factory,
    fake_scheduler: FakeScheduler,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Timeout-generated responses must not try to cancel the timeout job."""
    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="timeout",
        action="escalate",
        timestamp=timestamp,
        raw_response={"timeout_action": "escalate"},
    )

    # cancel_pending_response should NOT have been called for timeout channel
    assert len(fake_scheduler.remove_job_calls) == 0


@pytest.mark.asyncio
async def test_non_timeout_channel_cancels_timeout_job(
    service: InteractiveResponseService,
    db_factory,
    fake_scheduler: FakeScheduler,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Real (non-timeout) responses must cancel the pending timeout job."""
    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response={},
    )

    assert len(fake_scheduler.remove_job_calls) == 1
    assert fake_scheduler.remove_job_calls[0] == (
        f"interactive_timeout_{test_execution.id}_{test_step.id}"
    )


@pytest.mark.asyncio
async def test_resume_scheduled_when_execution_is_waiting(
    service: InteractiveResponseService,
    db_factory,
    fake_scheduler: FakeScheduler,
    test_execution: WorkflowExecution,
    test_step: PipelineStep,
) -> None:
    """Resume is scheduled immediately when execution is already 'waiting'."""
    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=test_execution.id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response={},
    )

    assert len(fake_scheduler.resume_calls) == 1
    assert fake_scheduler.resume_calls[0][0] == test_execution.id


@pytest.mark.asyncio
async def test_resume_not_scheduled_for_terminal_execution(
    service: InteractiveResponseService,
    db_factory,
    fake_scheduler: FakeScheduler,
    test_rule: Rule,
    test_step: PipelineStep,
) -> None:
    """Resume must not be scheduled when execution is already terminal."""
    db: Session = db_factory()
    try:
        execution = WorkflowExecution(rule_id=test_rule.id, status="completed")
        db.add(execution)
        db.commit()
        db.refresh(execution)
        exec_id = execution.id
    finally:
        db.close()

    timestamp = datetime.now(UTC)
    await service.record_response(
        execution_id=exec_id,
        step_id=test_step.id,
        channel="pwa_popup_text",
        action="escalate",
        timestamp=timestamp,
        raw_response={},
    )

    assert len(fake_scheduler.resume_calls) == 0
