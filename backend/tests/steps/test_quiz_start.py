"""Unit tests for QuizStartStep."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest

from backend.steps.builtin.quiz_start import QuizStartStep


@dataclass
class FakePipelineStep:
    id: int
    step_type: str
    config_json: dict
    label: str | None = None
    rule_id: int | None = None


@dataclass
class FakeWorkflowExecution:
    id: int
    status: str


@dataclass
class FakeTriggerContext:
    room_name: str | None = None
    sensor_id: str | None = None


@dataclass
class FakeServiceContainer:
    db_factory: Mock
    knowledge_delivery: Mock | None = None
    notification_dispatcher: Mock | None = None
    scheduler: Mock | None = None


@dataclass
class FakeQuiz:
    id: int
    title: str
    status: str
    questions: list
    voice_instruction: str = ""
    intro_voice_template: str = ""


class TestQuizStartStepMetadata:
    """Test QuizStartStep metadata."""

    def test_metadata_returns_correct_type_name(self):
        metadata = QuizStartStep.metadata()
        assert metadata.type_name == "quiz_start"

    def test_metadata_returns_correct_category(self):
        metadata = QuizStartStep.metadata()
        assert metadata.category == "flow"

    def test_metadata_default_max_questions(self):
        metadata = QuizStartStep.metadata()
        assert metadata.default_config["max_questions"] == 5

    def test_metadata_default_randomize_is_false(self):
        metadata = QuizStartStep.metadata()
        assert metadata.default_config["randomize_order"] is False

    def test_metadata_requires_quiz_id(self):
        metadata = QuizStartStep.metadata()
        assert "quiz_id" in metadata.config_schema["required"]


class TestQuizStartStepExecute:
    """Test QuizStartStep execute method."""

    @pytest.mark.asyncio
    async def test_execute_with_missing_knowledge_delivery_returns_error(self):
        """Missing service returns StepResult error."""
        handler = QuizStartStep()
        step = FakePipelineStep(id=1, step_type="quiz_start", config_json={"quiz_id": 1, "dedupe_hours": 0})
        execution = FakeWorkflowExecution(id=200, status="running")
        quiz = FakeQuiz(id=1, title="Quiz", status="approved", questions=[])
        mock_db = Mock()
        # First call: quiz lookup; second call: dedupe session lookup returns None
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [quiz, None]
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=None,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "knowledge delivery service not available" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_missing_quiz_id_returns_error(self):
        """Missing quiz_id in config returns error."""
        handler = QuizStartStep()
        step = FakePipelineStep(id=2, step_type="quiz_start", config_json={})
        execution = FakeWorkflowExecution(id=201, status="running")
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "quiz_id is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_quiz_not_found_returns_error(self):
        """Quiz not in DB returns error."""
        handler = QuizStartStep()
        step = FakePipelineStep(id=3, step_type="quiz_start", config_json={"quiz_id": 99})
        execution = FakeWorkflowExecution(id=202, status="running")
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_unapproved_quiz_returns_error(self):
        """Quiz in draft status returns error."""
        handler = QuizStartStep()
        step = FakePipelineStep(id=4, step_type="quiz_start", config_json={"quiz_id": 1})
        execution = FakeWorkflowExecution(id=203, status="running")
        quiz = FakeQuiz(id=1, title="Quiz", status="draft", questions=[])
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = quiz
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is False
        assert "not approved" in result.data["error"]

    @pytest.mark.asyncio
    async def test_execute_with_approved_quiz_returns_success(self):
        """Approved quiz delivery returns success with session_id."""
        handler = QuizStartStep()
        step = FakePipelineStep(
            id=5, step_type="quiz_start", config_json={"quiz_id": 1}, rule_id=10
        )
        execution = FakeWorkflowExecution(id=204, status="running")
        quiz = FakeQuiz(id=1, title="Quiz", status="approved", questions=[])
        mock_db = Mock()
        # First call: quiz lookup returns quiz; second call: dedupe session lookup returns None
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [quiz, None]
        delivery_svc = Mock()
        delivery_svc.start_quiz_session = AsyncMock(return_value=Mock(session_id=55))
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
            scheduler=None,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is True
        assert result.data["quiz_id"] == 1
        assert result.data["quiz_session_id"] == 55
        delivery_svc.start_quiz_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_dedupe_skips_delivery(self):
        """Recent completed session triggers dedupe skip."""
        handler = QuizStartStep()
        step = FakePipelineStep(
            id=6,
            step_type="quiz_start",
            config_json={"quiz_id": 1, "dedupe_hours": 12},
            rule_id=10,
        )
        execution = FakeWorkflowExecution(id=205, status="running")
        quiz = FakeQuiz(id=1, title="Quiz", status="approved", questions=[])
        recent_session = Mock(id=99, status="completed")
        mock_db = Mock()
        # First execute returns quiz, second returns a recent session (dedupe hit)
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [quiz, recent_session]
        delivery_svc = Mock()
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is True
        assert result.data["skipped"] is True
        assert result.data["reason"] == "dedupe"
        delivery_svc.start_quiz_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_zero_dedupe_hours_skips_check(self):
        """Zero dedupe_hours bypasses the dedupe query."""
        handler = QuizStartStep()
        step = FakePipelineStep(
            id=7,
            step_type="quiz_start",
            config_json={"quiz_id": 1, "dedupe_hours": 0},
            rule_id=10,
        )
        execution = FakeWorkflowExecution(id=206, status="running")
        quiz = FakeQuiz(id=1, title="Quiz", status="approved", questions=[])
        mock_db = Mock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = quiz
        delivery_svc = Mock()
        delivery_svc.start_quiz_session = AsyncMock(return_value=Mock(session_id=56))
        services = FakeServiceContainer(
            db_factory=Mock(return_value=mock_db),
            knowledge_delivery=delivery_svc,
            scheduler=None,
        )

        result = await handler.execute(step, execution, {}, FakeTriggerContext(), services)

        assert result.success is True
        delivery_svc.start_quiz_session.assert_called_once()
