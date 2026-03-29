"""Composable pipeline executor.

Orchestrates step-by-step execution of rule pipelines using the
:class:`StepRegistry` plugin system.  Each step type is a self-contained
handler registered at startup.  The executor is responsible only for
sequencing, branching, wait/resume, and error handling.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.steps import StepRegistry
from backend.steps.base import ServiceContainer, StepResult, TriggerContext

logger = get_logger(__name__)


class PipelineExecutor:
    """Execute a rule's composable pipeline steps in sequence.

    Each step handler is looked up from the :class:`StepRegistry` and
    receives a :class:`ServiceContainer` with all available services.
    """

    def __init__(
        self,
        db_session_factory,
        person_tracking=None,
        person_id_client=None,
        vision_provider=None,
        logic_provider=None,
        translation_provider=None,
        notification_dispatcher=None,
        ha_client=None,
        event_aggregator=None,
        scheduler=None,
        rag_service=None,
    ) -> None:
        self._services = ServiceContainer(
            db_factory=db_session_factory,
            person_tracking=person_tracking,
            person_id_client=person_id_client,
            vision_provider=vision_provider,
            logic_provider=logic_provider,
            translation_provider=translation_provider,
            notification_dispatcher=notification_dispatcher,
            ha_client=ha_client,
            event_aggregator=event_aggregator,
            scheduler=scheduler,
            rag_service=rag_service,
        )

    # Expose scheduler for injection after construction
    @property
    def _scheduler(self):
        return self._services.scheduler

    @_scheduler.setter
    def _scheduler(self, value):
        self._services.scheduler = value

    # -- public API -----------------------------------------------------------

    async def execute(
        self,
        rule: Rule,
        trigger: TriggerContext,
        db: Session,
    ) -> WorkflowExecution:
        """Run a rule's pipeline from the first step."""
        # Create event log
        event_log = EventLog(
            rule_id=rule.id,
            rule_name=rule.name,
            sensor_id=trigger.sensor_id,
            room_name=trigger.room_name,
            trigger_type=trigger.trigger_type,
            media_paths_json=trigger.media_paths,
            status="processing",
        )
        db.add(event_log)
        db.flush()

        # Create workflow execution
        pipeline_data = {
            "trigger": {
                "type": trigger.trigger_type,
                "sensor_id": trigger.sensor_id,
                "room_name": trigger.room_name,
                "media_paths": trigger.media_paths,
                "media_type": trigger.media_type,
            },
        }
        # Include webhook payload in pipeline data
        if trigger.webhook_payload:
            pipeline_data["trigger_input"] = trigger.webhook_payload

        local_tz = ZoneInfo(settings.get("app.timezone", "America/New_York"))
        now_local = datetime.now(local_tz)
        pipeline_data["system"] = {
            "local_time": now_local.strftime("%I:%M %p"),
            "local_date": now_local.strftime("%Y-%m-%d"),
            "local_day_of_week": now_local.strftime("%A"),
            "timezone": str(local_tz),
        }

        execution = WorkflowExecution(
            rule_id=rule.id,
            event_log_id=event_log.id,
            status="running",
            pipeline_data_json=pipeline_data,
        )
        db.add(execution)
        db.flush()

        event_log.workflow_execution_id = execution.id
        db.commit()
        db.refresh(execution)

        # Get ordered steps
        steps = sorted(
            [s for s in rule.steps if s.enabled],
            key=lambda s: s.order,
        )
        if not steps:
            execution.status = "completed"
            event_log.status = "completed"
            db.commit()
            logger.info("pipeline_no_steps", rule=rule.name)
            return execution

        return await self._run_steps(execution, steps, trigger, db)

    async def resume(self, execution_id: int, db: Session) -> WorkflowExecution:
        """Resume a waiting workflow execution from its current step."""
        execution = db.query(WorkflowExecution).get(execution_id)
        if not execution:
            raise ValueError(f"WorkflowExecution {execution_id} not found")

        if execution.status != "waiting":
            logger.warning(
                "resume_non_waiting",
                execution_id=execution_id,
                status=execution.status,
            )
            return execution

        rule = execution.rule
        steps = sorted(
            [s for s in rule.steps if s.enabled],
            key=lambda s: s.order,
        )

        current_order = None
        if execution.current_step_id:
            for s in steps:
                if s.id == execution.current_step_id:
                    current_order = s.order
                    break

        if current_order is not None:
            steps = [s for s in steps if s.order > current_order]

        execution.status = "running"
        execution.resume_at = None
        db.commit()

        trigger_data = (execution.pipeline_data_json or {}).get("trigger", {})
        trigger = TriggerContext(
            trigger_type="resume",
            sensor_id=trigger_data.get("sensor_id"),
            room_name=trigger_data.get("room_name"),
            media_paths=trigger_data.get("media_paths", []),
            media_type=trigger_data.get("media_type", "image"),
        )

        return await self._run_steps(execution, steps, trigger, db)

    # -- step execution -------------------------------------------------------

    async def _run_steps(
        self,
        execution: WorkflowExecution,
        steps: list[PipelineStep],
        trigger: TriggerContext,
        db: Session,
    ) -> WorkflowExecution:
        """Iterate through steps, handling branching and early exit."""
        pipeline_data: dict = dict(execution.pipeline_data_json or {})
        step_by_id = {s.id: s for s in steps}
        step_index = 0
        step_list = list(steps)
        override_step_id: int | None = None

        try:
            while step_index < len(step_list) or override_step_id is not None:
                if override_step_id is not None:
                    step = step_by_id.get(override_step_id)
                    override_step_id = None
                    if not step:
                        break
                else:
                    step = step_list[step_index]
                    step_index += 1

                execution.current_step_id = step.id
                db.commit()

                logger.info(
                    "step_executing",
                    rule=execution.rule.name,
                    step_type=step.step_type,
                    step_label=step.label,
                    order=step.order,
                )

                result = await self._execute_step(
                    step, execution, pipeline_data, trigger
                )

                pipeline_data.update(result.data)
                execution.pipeline_data_json = pipeline_data
                db.commit()

                # Handle wait
                if result.wait_until:
                    execution.status = "waiting"
                    execution.resume_at = result.wait_until
                    db.commit()
                    if self._services.scheduler:
                        self._services.scheduler.schedule_workflow_resume(
                            execution.id, result.wait_until
                        )
                    logger.info(
                        "pipeline_waiting",
                        execution_id=execution.id,
                        resume_at=result.wait_until.isoformat(),
                    )
                    return execution

                # Handle early exit
                if not result.should_continue:
                    execution.status = "completed"
                    event_log = (
                        db.query(EventLog)
                        .filter(EventLog.id == execution.event_log_id)
                        .first()
                    )
                    if event_log:
                        event_log.status = "ignored"
                        event_log.pipeline_data_json = pipeline_data
                    db.commit()
                    logger.info(
                        "pipeline_early_exit",
                        rule=execution.rule.name,
                        step=step.label or step.step_type,
                    )
                    return execution

                # Handle branching
                if result.next_step_id:
                    override_step_id = result.next_step_id

            # All steps completed
            execution.status = "completed"
            execution.pipeline_data_json = pipeline_data

            event_log = (
                db.query(EventLog)
                .filter(EventLog.id == execution.event_log_id)
                .first()
            )
            if event_log:
                if pipeline_data.get("_cooloff_triggered", False):
                    event_log.status = "completed"
                else:
                    event_log.status = "ignored"
                event_log.pipeline_data_json = pipeline_data
            db.commit()

            logger.info(
                "pipeline_completed",
                rule=execution.rule.name,
                cooloff_triggered=pipeline_data.get("_cooloff_triggered", False)
            )
            return execution

        except Exception as e:
            logger.error(
                "pipeline_error",
                rule=execution.rule.name,
                error=str(e),
                exc_info=True,
            )
            execution.status = "failed"
            execution.error = str(e)
            execution.pipeline_data_json = {**pipeline_data, "error": str(e)}
            event_log = (
                db.query(EventLog)
                .filter(EventLog.id == execution.event_log_id)
                .first()
            )
            if event_log:
                event_log.status = "failed"
                event_log.pipeline_data_json = {**pipeline_data, "error": str(e)}
            db.commit()
            return execution

    async def _execute_step(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Dispatch to the appropriate step handler via the StepRegistry."""
        handler = StepRegistry.get(step.step_type)
        if not handler:
            logger.warning("unknown_step_type", step_type=step.step_type)
            return StepResult(success=False, should_continue=False)

        return await handler.execute(
            step, execution, pipeline_data, trigger, self._services
        )
