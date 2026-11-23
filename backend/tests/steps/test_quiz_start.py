"""Unit tests for QuizStartStep."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from backend.steps.builtin.quiz_start import QuizStartStep
from backend.tests.factories.knowledge import (
    multiple_choice,
    seed_completed_session,
    seed_execution,
    seed_quiz,
)
from backend.tests.factories.knowledge_delivery import make_delivery


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


def _step(config: dict, step_id: int = 1) -> FakePipelineStep:
    return FakePipelineStep(id=step_id, step_type="quiz_start", config_json=config)


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
    """Execute against the real database: mocked sessions hid MultipleResultsFound and
    the detached lazy load of the quiz's questions."""

    @pytest.mark.asyncio
    async def test_missing_quiz_id_returns_error(self, db_factory):
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=Mock())

        result = await QuizStartStep().execute(
            _step({}),
            FakeWorkflowExecution(id=1, status="running"),
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.success is False
        assert "quiz_id is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_missing_quiz_returns_error(self, db_factory):
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=Mock())

        result = await QuizStartStep().execute(
            _step({"quiz_id": 999}),
            FakeWorkflowExecution(id=1, status="running"),
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.success is False
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_unapproved_quiz_returns_error(self, db_session, db_factory):
        quiz = seed_quiz(db_session, [multiple_choice("Q?", "A", "B")], status="draft")
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=Mock())

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id}),
            FakeWorkflowExecution(id=1, status="running"),
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.success is False
        assert "not approved" in result.data["error"]

    @pytest.mark.asyncio
    async def test_missing_delivery_service_returns_error(self, db_session, db_factory):
        quiz = seed_quiz(db_session, [multiple_choice("Q?", "A", "B")])
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=None)

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id, "dedupe_hours": 0}),
            FakeWorkflowExecution(id=1, status="running"),
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.success is False
        assert "knowledge delivery service not available" in result.data["error"]

    @pytest.mark.asyncio
    async def test_starts_session_parks_past_timeout_and_flags_cooloff(
        self, db_session, db_factory
    ):
        execution = seed_execution(db_session)
        quiz = seed_quiz(
            db_session,
            [multiple_choice("Who is Priya?", "Granddaughter", "Neighbour")],
        )
        delivery, ws, _scheduler = make_delivery(db_factory)
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=delivery)
        before = datetime.now(UTC)

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id, "session_timeout_minutes": 10}),
            execution,
            {"person_id": "resident-1"},
            FakeTriggerContext(),
            services,
        )

        assert result.success is True
        assert result.data["status"] == "started"
        assert result.data["quiz_session_id"] is not None
        assert result.data["_cooloff_triggered"] is True
        # The pipeline waits past the session timeout, so the session is terminal
        # before anything downstream runs.
        assert result.wait_until > before + timedelta(minutes=10)
        question = ws.of_type("quiz_question")[0]
        assert question["question_text"] == "Who is Priya?"

    @pytest.mark.asyncio
    async def test_dedupe_with_several_recent_completions_skips_with_latest(
        self, db_session, db_factory
    ):
        quiz = seed_quiz(db_session, [multiple_choice("Q?", "A", "B")])
        now = datetime.now(UTC)
        seed_completed_session(db_session, quiz, completed_at=now - timedelta(hours=3))
        latest = seed_completed_session(db_session, quiz, completed_at=now - timedelta(hours=1))
        delivery = Mock()
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=delivery)

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id, "dedupe_hours": 12}),
            FakeWorkflowExecution(id=1, status="running"),
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.success is True
        assert result.data == {
            "quiz_id": quiz.id,
            "quiz_session_id": None,
            "max_questions": 5,
            "status": "skipped_dedupe",
            "skipped": True,
            "reason": "dedupe",
            "prior_session_id": latest.id,
        }
        assert result.wait_until is None
        delivery.start_quiz_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_dedupe_hours_ignores_recent_completion(self, db_session, db_factory):
        execution = seed_execution(db_session)
        quiz = seed_quiz(db_session, [multiple_choice("Q?", "A", "B")])
        seed_completed_session(db_session, quiz, completed_at=datetime.now(UTC))
        delivery, _ws, _scheduler = make_delivery(db_factory)
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=delivery)

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id, "dedupe_hours": 0}),
            execution,
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.data["status"] == "started"

    @pytest.mark.asyncio
    async def test_quiz_without_questions_fails_without_a_session_row(self, db_session, db_factory):
        from backend.models.knowledge import QuizSession

        execution = seed_execution(db_session)
        quiz = seed_quiz(db_session, [])
        delivery, _ws, _scheduler = make_delivery(db_factory)
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=delivery)

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id}), execution, {}, FakeTriggerContext(), services
        )

        assert result.success is False
        assert "no questions" in result.data["error"]
        assert db_session.query(QuizSession).count() == 0

    @pytest.mark.asyncio
    async def test_rejects_unknown_interaction_mode(self, db_session, db_factory):
        quiz = seed_quiz(db_session, [multiple_choice("Q?", "A", "B")])
        services = FakeServiceContainer(db_factory=db_factory, knowledge_delivery=Mock())

        result = await QuizStartStep().execute(
            _step({"quiz_id": quiz.id, "interaction_mode": "exam"}),
            FakeWorkflowExecution(id=1, status="running"),
            {},
            FakeTriggerContext(),
            services,
        )

        assert result.success is False
        assert "interaction_mode" in result.data["error"]

    def test_metadata_defaults_to_gentle_mode_with_both_channels(self):
        metadata = QuizStartStep.metadata()
        assert metadata.default_config["interaction_mode"] == "gentle"
        assert metadata.default_config["channels"] == ["pwa", "voice"]
