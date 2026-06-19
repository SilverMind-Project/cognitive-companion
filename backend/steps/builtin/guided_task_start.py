"""Guided-task start pipeline step."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.guided_task.policy import resolve_policy
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


@StepRegistry.register
class GuidedTaskStartStep(StepHandler):
    """Pipeline step for starting a guided-task routine."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        default_timeout_s = settings.as_int("guided_task.step_timeout_s")
        return StepMetadata(
            type_name="guided_task_start",
            display_name="Guided Task Start",
            category="flow",
            icon="mdi-clipboard-list-outline",
            description="Start a guided-task routine through the companion surface.",
            config_schema={
                "type": "object",
                "properties": {
                    "routine_id": {"type": "integer"},
                    "require_presence": {"type": "boolean", "default": True},
                    "summon_timeout_s": {
                        "type": "integer",
                        "default": default_timeout_s,
                        "minimum": 1,
                    },
                    "dedupe_hours": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "description": "Skip if this routine completed within N hours.",
                    },
                },
                "required": ["routine_id"],
            },
            default_config={
                "require_presence": True,
                "summon_timeout_s": default_timeout_s,
                "dedupe_hours": 0,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "routine_id": {"type": "integer"},
                    "guided_session_id": {"type": "integer"},
                    "status": {"type": "string"},
                    "skipped": {"type": "boolean"},
                    "reason": {"type": "string"},
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
        routine_id = config.get("routine_id")
        if not routine_id:
            return StepResult(success=False, data={"error": "routine_id is required"})
        if services.guided_task is None:
            return StepResult(success=False, data={"error": "guided task service not available"})

        require_presence = bool(config.get("require_presence", True))
        summon_timeout_s = int(
            config.get("summon_timeout_s") or settings.as_int("guided_task.step_timeout_s")
        )
        dedupe_hours = int(config.get("dedupe_hours", 0) or 0)

        db: Session = services.db_factory()
        try:
            routine = db.execute(
                select(Routine).where(Routine.id == routine_id)
            ).scalar_one_or_none()
            if routine is None:
                return StepResult(success=False, data={"error": f"Routine {routine_id} not found"})

            if dedupe_hours > 0:
                cutoff = datetime.now(UTC) - timedelta(hours=dedupe_hours)
                recent = db.execute(
                    select(GuidedSession).where(
                        GuidedSession.routine_id == routine_id,
                        GuidedSession.status == "completed",
                        GuidedSession.completed_at >= cutoff,
                    )
                ).scalar_one_or_none()
                if recent is not None:
                    logger.info(
                        "guided_task_dedupe_skipped",
                        routine_id=routine_id,
                        session_id=recent.id,
                    )
                    return StepResult(
                        data={
                            "skipped": True,
                            "reason": "dedupe",
                            "prior_session_id": recent.id,
                        }
                    )

            first_step = (
                db.execute(
                    select(RoutineStep)
                    .where(RoutineStep.routine_id == routine_id)
                    .order_by(RoutineStep.ord)
                )
                .scalars()
                .first()
            )
            session_timeout_s = (
                resolve_policy(routine, first_step, settings).step_timeout_s
                if first_step is not None
                else settings.as_int("guided_task.step_timeout_s")
            )
            person_id = routine.person_id
        finally:
            db.close()

        session = await services.guided_task.request_start(
            routine_id,
            person_id,
            execution_id=execution.id,
            require_presence=require_presence,
            summon_timeout_s=summon_timeout_s,
        )
        wait_until = datetime.now(UTC) + timedelta(seconds=max(summon_timeout_s, session_timeout_s))
        return StepResult(
            data={
                "routine_id": routine_id,
                "guided_session_id": session.id,
                "status": session.status,
            },
            wait_until=wait_until,
        )
