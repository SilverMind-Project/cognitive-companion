"""Quiz start pipeline step. Delivers an interactive quiz via PWA and voice."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.knowledge import Quiz, QuizSession
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.interactive_session import schedule_session_timeout
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

if TYPE_CHECKING:
    from backend.services.knowledge.delivery_service import KnowledgeDeliveryService

logger = get_logger(__name__)


@StepRegistry.register
class QuizStartStep(StepHandler):
    """Pipeline step for starting an interactive quiz session."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="quiz_start",
            display_name="Quiz Start",
            category="flow",
            icon="mdi-help-box-outline",
            description="Deliver an interactive quiz via the companion PWA.",
            config_schema={
                "type": "object",
                "properties": {
                    "quiz_id": {"type": "integer"},
                    "max_questions": {"type": "integer", "default": 5},
                    "randomize_order": {"type": "boolean", "default": False},
                    "session_timeout_minutes": {"type": "integer", "default": 10},
                    "trigger_cooloff": {"type": "boolean", "default": True},
                    "dedupe_hours": {
                        "type": "integer",
                        "default": 12,
                        "description": "Skip if this quiz was completed within N hours.",
                    },
                    "voice_instruction": {
                        "type": "string",
                        "default": "",
                        "description": "Override the Gemini Live system instruction for this quiz session.",
                    },
                },
                "required": ["quiz_id"],
            },
            default_config={
                "max_questions": 5,
                "randomize_order": False,
                "session_timeout_minutes": 10,
                "trigger_cooloff": True,
                "dedupe_hours": 12,
                "voice_instruction": "",
            },
            output_schema={
                "type": "object",
                "properties": {
                    "quiz_id": {"type": "integer"},
                    "quiz_session_id": {"type": "integer"},
                    "max_questions": {"type": "integer"},
                },
            },
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}
        quiz_id = config.get("quiz_id")
        if not quiz_id:
            return StepResult(success=False, data={"error": "quiz_id is required"})

        max_questions = config.get("max_questions", 5)
        randomize_order = config.get("randomize_order", False)
        timeout_minutes = config.get("session_timeout_minutes", 10)
        dedupe_hours = config.get("dedupe_hours", 12)
        voice_instruction = config.get("voice_instruction", "")

        # Load the quiz
        db: Session = services.db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                return StepResult(success=False, data={"error": f"Quiz {quiz_id} not found"})
            if quiz.status != "approved":
                return StepResult(
                    success=False,
                    data={"error": f"Quiz {quiz_id} is not approved (status: {quiz.status})"},
                )

            # Dedupe check
            if dedupe_hours > 0:
                cutoff = datetime.now(UTC) - timedelta(hours=dedupe_hours)
                recent = db.execute(
                    select(QuizSession).where(
                        QuizSession.quiz_id == quiz_id,
                        QuizSession.status == "completed",
                        QuizSession.completed_at >= cutoff,
                    )
                ).scalar_one_or_none()
                if recent:
                    logger.info("quiz_dedupe_skipped", quiz_id=quiz_id, session_id=recent.id)
                    return StepResult(
                        data={"skipped": True, "reason": "dedupe", "prior_session_id": recent.id}
                    )
        finally:
            db.close()

        # Delivery
        delivery_svc = services.knowledge_delivery
        if delivery_svc is None:
            return StepResult(
                success=False, data={"error": "knowledge delivery service not available"}
            )

        result = await delivery_svc.start_quiz_session(
            quiz=quiz,
            execution_id=execution.id,
            rule_id=step.rule_id,
            voice_instruction=voice_instruction or None,
            max_questions=max_questions,
            randomize_order=randomize_order,
            session_timeout_minutes=timeout_minutes,
        )

        # Schedule timeout
        timeout_at = datetime.now(UTC) + timedelta(minutes=timeout_minutes)
        schedule_session_timeout(
            services.scheduler,
            job_id=f"quiz_timeout_{result.session_id}",
            run_at=timeout_at,
            finalize=self._handle_timeout,
            args=[result.session_id, delivery_svc],
        )

        logger.info(
            "quiz_start_step_executed",
            quiz_id=quiz_id,
            session_id=result.session_id,
        )
        return StepResult(
            data={
                "quiz_id": quiz_id,
                "quiz_session_id": result.session_id,
                "max_questions": max_questions,
            },
            wait_until=timeout_at,
        )

    @staticmethod
    async def _handle_timeout(session_id: int, delivery_svc: KnowledgeDeliveryService) -> None:
        """Handle quiz session timeout."""
        delivery_svc._update_session_status(session_id, "timed_out")
        logger.info("quiz_session_timed_out", session_id=session_id)
