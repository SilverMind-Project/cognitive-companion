"""Composable pipeline executor.

Orchestrates step-by-step execution of rule pipelines using the
:class:`StepRegistry` plugin system.  Each step type is a self-contained
handler registered at startup.  The executor is responsible only for
sequencing, branching, wait/resume, error handling, per-step timing, and
enforcing per-rule execution timeouts.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

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

    Timing data is written into ``pipeline_data_json`` under two keys:

    * ``_pipeline`` - ``{"started_at": ISO, "completed_at": ISO | null}``
    * ``_step_timings`` - list of per-step dicts with ``started_at``,
      ``completed_at``, ``elapsed_seconds``, and ``success``.

    When a rule sets ``execution_timeout_minutes > 0`` the entire pipeline
    (excluding wait periods) is cancelled if it exceeds that duration and the
    execution is marked ``"failed"`` with a descriptive error.
    """

    def __init__(
        self,
        db_session_factory,
        person_tracking=None,
        person_id_client=None,
        vision_provider=None,
        notification_dispatcher=None,
        ha_client=None,
        event_aggregator=None,
        scheduler=None,
        rag_service=None,
        llm_model_registry=None,
        scene_analysis_client=None,
        activity_session_service=None,
        daily_report_service=None,
        object_trend_client=None,
    ) -> None:
        self._services = ServiceContainer(
            db_factory=db_session_factory,
            person_tracking=person_tracking,
            person_id_client=person_id_client,
            vision_provider=vision_provider,
            notification_dispatcher=notification_dispatcher,
            ha_client=ha_client,
            event_aggregator=event_aggregator,
            scheduler=scheduler,
            rag_service=rag_service,
            llm_model_registry=llm_model_registry,
            scene_analysis_client=scene_analysis_client,
            activity_session_service=activity_session_service,
            daily_report_service=daily_report_service,
            object_trend_client=object_trend_client,
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
        """Run a rule's pipeline from the first step.

        Applies ``rule.execution_timeout_minutes`` as a hard wall-clock limit
        over the active execution (waits do not count against the limit because
        the coroutine is not running during a wait).
        """
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

        local_tz = ZoneInfo(settings.get("app.timezone", "America/New_York"))
        now_local = datetime.now(local_tz)
        now_utc = datetime.now(UTC)

        pipeline_data: dict = {
            "trigger": {
                "type": trigger.trigger_type,
                "sensor_id": trigger.sensor_id,
                "room_name": trigger.room_name,
                "media_paths": trigger.media_paths,
                "media_type": trigger.media_type,
            },
            "system": {
                "local_time": now_local.strftime("%I:%M %p"),
                "local_date": now_local.strftime("%Y-%m-%d"),
                "local_day_of_week": now_local.strftime("%A"),
                "timezone": str(local_tz),
            },
            "_pipeline": {
                "started_at": now_utc.isoformat(),
                "completed_at": None,
            },
            "_step_timings": [],
        }

        if trigger.webhook_payload:
            pipeline_data["trigger_input"] = trigger.webhook_payload

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

        steps = sorted(
            [s for s in rule.steps if s.enabled],
            key=lambda s: s.order,
        )
        if not steps:
            completed_at = datetime.now(UTC)
            execution.status = "completed"
            execution.completed_at = completed_at
            _mark_pipeline_completed(execution, completed_at)
            event_log.status = "completed"
            db.commit()
            logger.info("pipeline_no_steps", rule=rule.name)
            return execution

        timeout_seconds: float | None = (
            rule.execution_timeout_minutes * 60 if rule.execution_timeout_minutes > 0 else None
        )

        try:
            return await asyncio.wait_for(
                self._run_steps(execution, steps, trigger, db),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return self._handle_timeout(rule, execution, db)

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

        timeout_seconds: float | None = (
            rule.execution_timeout_minutes * 60 if rule.execution_timeout_minutes > 0 else None
        )

        try:
            return await asyncio.wait_for(
                self._run_steps(execution, steps, trigger, db),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return self._handle_timeout(rule, execution, db)

    # -- step execution -------------------------------------------------------

    async def _run_steps(
        self,
        execution: WorkflowExecution,
        steps: list[PipelineStep],
        trigger: TriggerContext,
        db: Session,
    ) -> WorkflowExecution:
        """Iterate through steps, handling branching, timing, and early exit.

        ``execution.pipeline_data_json`` is wrapped by
        :class:`sqlalchemy.ext.mutable.MutableDict` (see the column definition
        on :class:`WorkflowExecution`). All writes in this method go through
        that tracked reference so SQLAlchemy flushes the updated JSON on every
        ``db.commit()``. Do not rebind a local plain-dict copy: mutations to a
        detached copy would not be flagged dirty, and because the session
        factory runs with ``expire_on_commit=False`` the row would silently
        drift out of sync with in-memory state.

        Nested mutations such as ``pipeline_data["_pipeline"]["completed_at"]``
        are invisible to ``MutableDict``; call :func:`_mark_pipeline_completed`
        (which uses :func:`flag_modified`) for those.
        """
        pipeline_data = execution.pipeline_data_json
        if pipeline_data is None:
            execution.pipeline_data_json = {}
            pipeline_data = execution.pipeline_data_json

        # Preserve timings across resume cycles
        step_timings: list = list(pipeline_data.get("_step_timings", []))

        step_by_id = {s.id: s for s in steps}
        step_index = 0
        step_list = list(steps)
        override_step_id: int | None = None

        # Tracked so the except-block can record a timing entry for a failed step
        _active_step: PipelineStep | None = None
        _active_step_started_at: datetime | None = None

        try:
            while step_index < len(step_list) or override_step_id is not None:
                if override_step_id is not None:
                    step = step_by_id.get(override_step_id)
                    target_id = override_step_id
                    override_step_id = None
                    if not step:
                        logger.warning(
                            "branch_target_not_found",
                            rule=execution.rule.name,
                            target_step_id=target_id,
                        )
                        break
                    try:
                        linear_pos = step_list.index(step)
                        step_index = linear_pos + 1
                    except ValueError:
                        pass
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

                _active_step = step
                _active_step_started_at = datetime.now(UTC)

                result = await self._execute_step(step, execution, pipeline_data, trigger)

                step_completed_at = datetime.now(UTC)
                step_timings.append(
                    _make_step_timing(
                        step, _active_step_started_at, step_completed_at, result.success
                    )
                )
                # Signal to the except-block that this step's timing is already saved
                _active_step_started_at = None

                # Merge step output into the tracked dict. ``update`` and
                # ``__setitem__`` on a MutableDict both fire ``changed()``,
                # which marks the JSON column dirty for the next flush.
                pipeline_data.update(result.data)
                pipeline_data["_step_timings"] = step_timings
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

                # Handle early exit.
                #
                # ``should_continue=False`` carries two distinct meanings:
                #
                # * ``success=True`` is an intentional skip (e.g. a filter
                #   step deciding the rule should not fire). The execution is
                #   a normal ``completed`` and the event log is ``ignored``
                #   so rate-limit / cool-off logic treats it as a no-op.
                # * ``success=False`` is an error (e.g. an unknown step type
                #   returning a sentinel ``StepResult``). Both the execution
                #   and the event log must be marked ``failed`` so operators
                #   can find it in the UI and alerting stays accurate.
                if not result.should_continue:
                    completed_at = datetime.now(UTC)
                    if result.success:
                        execution.status = "completed"
                        event_log_status = "ignored"
                    else:
                        execution.status = "failed"
                        event_log_status = "failed"
                    execution.completed_at = completed_at
                    _mark_pipeline_completed(execution, completed_at)

                    skip_reason = result.data.get("skip_reason")

                    event_log = (
                        db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
                    )
                    if event_log:
                        event_log.status = event_log_status
                        event_log.pipeline_data_json = dict(pipeline_data)
                    db.commit()
                    logger.info(
                        "pipeline_early_exit",
                        rule=execution.rule.name,
                        step=step.label or step.step_type,
                        event_log_status=event_log_status,
                        skip_reason=skip_reason,
                    )
                    return execution

                # Handle branching
                if result.next_step_id:
                    override_step_id = result.next_step_id

            # All steps completed
            completed_at = datetime.now(UTC)
            execution.status = "completed"
            execution.completed_at = completed_at
            pipeline_data["_step_timings"] = step_timings
            _mark_pipeline_completed(execution, completed_at)

            event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
            if event_log:
                if pipeline_data.get("_cooloff_triggered", False):
                    event_log.status = "completed"
                else:
                    event_log.status = "ignored"
                event_log.pipeline_data_json = dict(pipeline_data)
            db.commit()

            logger.info(
                "pipeline_completed",
                rule=execution.rule.name,
                cooloff_triggered=pipeline_data.get("_cooloff_triggered", False),
            )
            return execution

        except Exception as e:
            completed_at = datetime.now(UTC)

            # Record timing for the step that raised, if not already saved
            if _active_step is not None and _active_step_started_at is not None:
                step_timings.append(
                    _make_step_timing(
                        _active_step,
                        _active_step_started_at,
                        completed_at,
                        success=False,
                        error=str(e),
                    )
                )

            logger.error(
                "pipeline_error",
                rule=execution.rule.name,
                error=str(e),
                exc_info=True,
            )
            pipeline_data["_step_timings"] = step_timings
            pipeline_data["error"] = str(e)
            _mark_pipeline_completed(execution, completed_at)

            execution.status = "failed"
            execution.completed_at = completed_at
            execution.error = str(e)

            event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
            if event_log:
                event_log.status = "failed"
                event_log.pipeline_data_json = dict(pipeline_data)
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

        return await handler.execute(step, execution, pipeline_data, trigger, self._services)

    # -- helpers --------------------------------------------------------------

    def _handle_timeout(
        self,
        rule: Rule,
        execution: WorkflowExecution,
        db: Session,
    ) -> WorkflowExecution:
        """Mark the execution as failed due to timeout and persist the state."""
        completed_at = datetime.now(UTC)
        error_msg = (
            f"Pipeline timed out after {rule.execution_timeout_minutes} minute"
            f"{'s' if rule.execution_timeout_minutes != 1 else ''}"
        )

        # Reload execution from DB to pick up whatever was last committed by
        # the cancelled ``_run_steps`` coroutine, then mutate the tracked
        # attribute in place so the MutableDict records the change.
        db.expire(execution)
        pipeline_data = execution.pipeline_data_json
        if pipeline_data is None:
            execution.pipeline_data_json = {}
            pipeline_data = execution.pipeline_data_json

        pipeline_data["error"] = error_msg
        _mark_pipeline_completed(execution, completed_at)

        execution.status = "failed"
        execution.completed_at = completed_at
        execution.error = error_msg

        event_log = db.query(EventLog).filter(EventLog.id == execution.event_log_id).first()
        if event_log:
            event_log.status = "failed"
        db.commit()

        logger.error(
            "pipeline_timeout",
            rule=rule.name,
            execution_id=execution.id,
            timeout_minutes=rule.execution_timeout_minutes,
        )
        return execution


def _make_step_timing(
    step: PipelineStep,
    started_at: datetime,
    completed_at: datetime,
    success: bool,
    error: str | None = None,
) -> dict:
    """Build a timing entry dict for a single pipeline step."""
    entry: dict = {
        "step_id": step.id,
        "step_type": step.step_type,
        "label": step.label,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "elapsed_seconds": round((completed_at - started_at).total_seconds(), 3),
        "success": success,
    }
    if error is not None:
        entry["error"] = error
    return entry


def _mark_pipeline_completed(execution: WorkflowExecution, completed_at: datetime) -> None:
    """Stamp ``pipeline_data_json['_pipeline']['completed_at']`` and mark dirty.

    This mutates a nested dict inside the ``MutableDict``-wrapped JSON
    column. ``MutableDict`` only tracks top-level ``__setitem__`` / ``update``
    calls, so nested writes must be reported to SQLAlchemy explicitly via
    :func:`flag_modified` or the next flush will miss the change.
    """
    pipeline_data = execution.pipeline_data_json
    if pipeline_data is None:
        return
    block = pipeline_data.setdefault("_pipeline", {})
    block["completed_at"] = completed_at.isoformat()
    flag_modified(execution, "pipeline_data_json")
