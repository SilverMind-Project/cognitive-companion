"""Quiz start pipeline step. Delivers an interactive quiz via PWA and voice."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.core.exceptions import ValidationError
from backend.core.logging import get_logger
from backend.models.knowledge import Quiz, QuizSession
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.knowledge.voice_instructions import QUIZ_INTERACTION_MODES
from backend.steps import StepRegistry
from backend.steps._helpers import make_trigger_vars, resolve_person_id, resolve_surface_id
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

# The pipeline parks until the quiz ends; the delivery service resumes it on completion
# or timeout. This margin past the session timeout is only the executor's backstop, so
# the session is always marked timed_out before anything downstream runs.
_RESUME_BACKSTOP = timedelta(seconds=60)


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
                    "channels": {
                        "type": "array",
                        "items": {"enum": ["pwa", "voice"]},
                        "minItems": 1,
                        "default": ["pwa", "voice"],
                    },
                    "interaction_mode": {
                        "type": "string",
                        "enum": list(QUIZ_INTERACTION_MODES),
                        "default": "gentle",
                        "description": (
                            "gentle: errorless learning, no right/wrong feedback or score "
                            "shown to the senior (answers are still recorded). standard: "
                            "graded feedback and a score."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Resident taking the quiz; defaults to the person in the "
                            "trigger or upstream steps. Supports {{template}} syntax."
                        ),
                    },
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
                        "description": (
                            "Added to the companion's persona for this quiz session. "
                            "Supports {{template}} syntax."
                        ),
                    },
                },
                "required": ["quiz_id"],
            },
            default_config={
                "channels": ["pwa", "voice"],
                "interaction_mode": "gentle",
                "person_id": "",
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
                    "quiz_session_id": {
                        "type": ["integer", "null"],
                        "description": "This run's session; null when skipped.",
                    },
                    "max_questions": {"type": "integer"},
                    "status": {"type": "string", "enum": ["started", "skipped_dedupe"]},
                    "skipped": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "prior_session_id": {"type": ["integer", "null"]},
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

        interaction_mode = config.get("interaction_mode", "gentle")
        if interaction_mode not in QUIZ_INTERACTION_MODES:
            return StepResult(
                success=False,
                data={"error": f"interaction_mode must be one of {list(QUIZ_INTERACTION_MODES)}"},
            )
        max_questions = config.get("max_questions", 5)
        dedupe_hours = config.get("dedupe_hours", 12)

        db: Session = services.db_factory()
        try:
            # Questions are eager-loaded: delivery reads them after this session closes,
            # and a lazy load on the detached quiz would raise.
            quiz = db.execute(
                select(Quiz).options(selectinload(Quiz.questions)).where(Quiz.id == quiz_id)
            ).scalar_one_or_none()
            if quiz is None:
                return StepResult(success=False, data={"error": f"Quiz {quiz_id} not found"})
            if quiz.status != "approved":
                return StepResult(
                    success=False,
                    data={"error": f"Quiz {quiz_id} is not approved (status: {quiz.status})"},
                )

            if dedupe_hours > 0:
                cutoff = datetime.now(UTC) - timedelta(hours=dedupe_hours)
                recent = (
                    db.execute(
                        select(QuizSession)
                        .where(
                            QuizSession.quiz_id == quiz_id,
                            QuizSession.status == "completed",
                            QuizSession.completed_at >= cutoff,
                        )
                        .order_by(QuizSession.completed_at.desc())
                        .limit(1)
                    )
                    .scalars()
                    .first()
                )
                if recent is not None:
                    logger.info("quiz_dedupe_skipped", quiz_id=quiz_id, session_id=recent.id)
                    return StepResult(
                        data={
                            "quiz_id": quiz_id,
                            "quiz_session_id": None,
                            "max_questions": max_questions,
                            "status": "skipped_dedupe",
                            "skipped": True,
                            "reason": "dedupe",
                            "prior_session_id": recent.id,
                        }
                    )
        finally:
            db.close()

        delivery_svc = services.knowledge_delivery
        if delivery_svc is None:
            return StepResult(
                success=False, data={"error": "knowledge delivery service not available"}
            )

        senior_id = resolve_person_id(config, pipeline_data, make_trigger_vars(trigger))
        try:
            result = await delivery_svc.start_quiz_session(
                quiz=quiz,
                execution_id=execution.id,
                rule_id=step.rule_id,
                channels=config.get("channels") or ["pwa", "voice"],
                voice_instruction=config.get("voice_instruction") or None,
                max_questions=max_questions,
                randomize_order=config.get("randomize_order", False),
                session_timeout_minutes=config.get("session_timeout_minutes", 10),
                interaction_mode=interaction_mode,
                senior_id=senior_id,
                template_data=pipeline_data,
                trigger_vars=make_trigger_vars(trigger),
                surface_id=await resolve_surface_id(services, senior_id),
            )
        except ValidationError as exc:
            return StepResult(success=False, data={"error": exc.message})

        logger.info("quiz_start_step_executed", quiz_id=quiz_id, session_id=result.session_id)
        result_data: dict = {
            "quiz_id": quiz_id,
            "quiz_session_id": result.session_id,
            "max_questions": max_questions,
            "status": "started",
            "skipped": False,
            "prior_session_id": None,
        }
        if config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True
        timeout_at = result.timeout_at or datetime.now(UTC)
        return StepResult(data=result_data, wait_until=timeout_at + _RESUME_BACKSTOP)
