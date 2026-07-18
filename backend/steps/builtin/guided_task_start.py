"""Guided-task start pipeline step."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import ConflictError
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
                    "prior_session_id": {"type": "integer"},
                    "parked_until": {"type": "string"},
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
                recent = (
                    db.execute(
                        select(GuidedSession)
                        .where(
                            GuidedSession.routine_id == routine_id,
                            GuidedSession.status == "completed",
                            GuidedSession.completed_at >= cutoff,
                        )
                        .order_by(GuidedSession.completed_at.desc())
                        .limit(1)
                    )
                    .scalars()
                    .first()
                )
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

            routine_steps = (
                db.execute(
                    select(RoutineStep)
                    .where(RoutineStep.routine_id == routine_id)
                    .order_by(RoutineStep.ord)
                )
                .scalars()
                .all()
            )
            routine_budget_s = 0
            for routine_step in routine_steps:
                step_policy = resolve_policy(routine, routine_step, settings)
                routine_budget_s += step_policy.step_timeout_s * step_policy.max_step_attempts
            person_id = routine.person_id
        finally:
            db.close()

        summon_budget_s = summon_timeout_s if require_presence else 0
        resume_grace_s = settings.as_int("guided_task.resume_grace_s")
        max_pipeline_park_s = settings.as_int("guided_task.max_pipeline_park_s")
        park_s = min(
            summon_budget_s + routine_budget_s + resume_grace_s,
            max_pipeline_park_s,
        )

        try:
            session = await services.guided_task.request_start(
                routine_id,
                person_id,
                execution_id=execution.id,
                require_presence=require_presence,
                summon_timeout_s=summon_timeout_s,
            )
        except ConflictError:
            live_session = services.guided_task.get_live_session_for_person(person_id)
            logger.info(
                "guided_task_live_session_skipped",
                routine_id=routine_id,
                person_id=person_id,
                live_session_id=live_session.id if live_session is not None else None,
            )
            return StepResult(
                data={
                    "skipped": True,
                    "reason": "live_session",
                    "prior_session_id": live_session.id if live_session is not None else None,
                }
            )

        parked_until = datetime.now(UTC) + timedelta(seconds=park_s)
        return StepResult(
            data={
                "routine_id": routine_id,
                "guided_session_id": session.id,
                "status": session.status,
                "parked_until": parked_until.isoformat(),
            },
            wait_until=parked_until,
        )
