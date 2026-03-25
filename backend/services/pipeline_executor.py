"""Composable pipeline executor.

Replaces the hardcoded linear pipeline with a step-by-step executor
that processes rules through their configured :class:`PipelineStep` sequence.
Each step type has a dedicated handler that reads from and writes to a shared
``pipeline_data`` dict carried through the execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.event import EventLog
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.models.rule import Rule
from backend.services.condition_evaluator import ConditionEvaluator

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class TriggerContext:
    """Metadata about what triggered a pipeline execution."""

    trigger_type: str  # sensor_event, cron, manual, resume
    sensor_id: str | None = None
    room_name: str | None = None
    media_paths: list[str] = field(default_factory=list)
    media_type: str = "image"


@dataclass
class StepResult:
    """Output of a single pipeline step."""

    success: bool = True
    data: dict = field(default_factory=dict)
    should_continue: bool = True
    next_step_id: int | None = None
    wait_until: datetime | None = None


# ---------------------------------------------------------------------------
# Response format templates for logic_reasoning step
# ---------------------------------------------------------------------------

RESPONSE_FORMAT_TEMPLATES: dict[str, str] = {
    "default": (
        "Respond in JSON with keys: is_notification_needed (bool), "
        "user_notification (str), reasoning (str)"
    ),
    "activity_detection": (
        "Respond in JSON with keys: activities (list of objects with "
        "person_id, activity_type, confidence)"
    ),
}


# ---------------------------------------------------------------------------
# Pipeline executor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """Execute a rule's composable pipeline steps in sequence.

    Each step handler receives the accumulated ``pipeline_data`` dict and
    returns a :class:`StepResult`.  The executor merges result data back into
    the pipeline state, handles branching (condition steps), and persists
    execution progress to allow wait/resume across process restarts.
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
    ) -> None:
        self._db_factory = db_session_factory
        self._person_tracking = person_tracking
        self._person_id = person_id_client
        self._vision = vision_provider
        self._logic = logic_provider
        self._translation = translation_provider
        self._notifier = notification_dispatcher
        self._ha = ha_client
        self._aggregator = event_aggregator
        self._scheduler = scheduler
        self._condition_eval = ConditionEvaluator()

    # -- public API -----------------------------------------------------------

    async def execute(
        self,
        rule: Rule,
        trigger: TriggerContext,
        db: Session,
    ) -> WorkflowExecution:
        """Run a rule's pipeline from the first step.

        Creates an :class:`EventLog` row and a :class:`WorkflowExecution` row,
        then iterates through the pipeline steps.
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

        # Create workflow execution
        execution = WorkflowExecution(
            rule_id=rule.id,
            event_log_id=event_log.id,
            status="running",
            pipeline_data_json={
                "trigger": {
                    "type": trigger.trigger_type,
                    "sensor_id": trigger.sensor_id,
                    "room_name": trigger.room_name,
                    "media_paths": trigger.media_paths,
                    "media_type": trigger.media_type,
                },
            },
        )
        db.add(execution)
        db.flush()

        # Link event log to execution
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

        # Find the step AFTER the current one (which was the wait step)
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

        # Reconstruct trigger context from pipeline_data
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

        # Build a lookup for branching
        step_by_id = {s.id: s for s in steps}

        # For linear iteration
        step_index = 0
        step_list = list(steps)
        override_step_id: int | None = None

        try:
            while step_index < len(step_list) or override_step_id is not None:
                # Determine which step to execute
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

                result = await self._execute_step(step, execution, pipeline_data, trigger)

                # Merge result data
                pipeline_data.update(result.data)
                execution.pipeline_data_json = pipeline_data
                db.commit()

                # Handle wait
                if result.wait_until:
                    execution.status = "waiting"
                    execution.resume_at = result.wait_until
                    db.commit()
                    # Schedule resume
                    if self._scheduler:
                        self._scheduler.schedule_workflow_resume(
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
                event_log.status = "completed"
                event_log.pipeline_data_json = pipeline_data
            db.commit()

            logger.info("pipeline_completed", rule=execution.rule.name)
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
        """Dispatch to the appropriate step handler by type."""
        handlers = {
            "person_identification": self._step_person_identification,
            "vision_analysis": self._step_vision_analysis,
            "logic_reasoning": self._step_logic_reasoning,
            "translation": self._step_translation,
            "notification": self._step_notification,
            "ha_action": self._step_ha_action,
            "activity_detection": self._step_activity_detection,
            "wait": self._step_wait,
            "condition": self._step_condition,
            "verification": self._step_verification,
        }
        handler = handlers.get(step.step_type)
        if not handler:
            logger.warning("unknown_step_type", step_type=step.step_type)
            return StepResult(success=False, should_continue=False)

        return await handler(step, execution, pipeline_data, trigger)

    # -- step handlers --------------------------------------------------------

    async def _step_person_identification(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Identify persons in camera frames."""
        if not self._person_tracking:
            return StepResult(data={"person_detections": []})

        config = step.config_json or {}
        media_paths = list(trigger.media_paths)

        # Gather additional camera images if aggregator available
        additional_sensors = config.get("additional_sensor_ids", [])
        if additional_sensors and self._aggregator:
            for sensor_id in additional_sensors:
                extra = await self._aggregator.get_recent_images(sensor_id, limit=3)
                media_paths.extend(extra)

        room_name = trigger.room_name or "Unknown"
        sensor_id = trigger.sensor_id or "unknown"

        detections = await self._person_tracking.process_camera_event(
            sensor_id=sensor_id,
            media_paths=media_paths,
            room_name=room_name,
            include_annotated_image=config.get("include_annotated_image", False),
        )

        detection_dicts = [d.dict() for d in detections]
        result_data: dict = {"person_detections": detection_dicts}

        # Store annotated image if available
        if detections and hasattr(detections[0], "annotated_image"):
            annotated = getattr(detections[0], "annotated_image", None)
            if annotated:
                result_data["annotated_image"] = annotated

        # Check target person filter
        target_persons = config.get("target_persons", [])
        min_confidence = config.get("min_confidence", 0.0)

        if target_persons:
            detected_ids = {
                d.person_id
                for d in detections
                if d.confidence >= min_confidence
            }
            if not detected_ids.intersection(set(target_persons)):
                result_data["skip_reason"] = "target_person_not_detected"
                return StepResult(
                    data=result_data,
                    should_continue=False,
                )

        return StepResult(data=result_data)

    async def _step_vision_analysis(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Run vision LLM analysis on media."""
        if not self._vision:
            return StepResult(data={"vision_response": ""})

        config = step.config_json or {}
        prompt = config.get("prompt", "Describe what you see in this image.")
        media_paths = trigger.media_paths

        # Optionally use annotated image from person-ID step
        if config.get("use_annotated_image") and pipeline_data.get("annotated_image"):
            # The annotated image is base64 — vision provider needs to handle it
            pass  # media_paths remain as-is; annotated image info is in pipeline_data

        vision_response = await self._vision.call(
            prompt=prompt,
            media_paths=media_paths,
            media_type=trigger.media_type,
        )
        return StepResult(data={"vision_response": vision_response})

    async def _step_logic_reasoning(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Run logic/reasoning LLM step."""
        if not self._logic:
            return StepResult(data={"logic_response": {}})

        config = step.config_json or {}
        prompt = config.get("prompt", "")
        include_context = config.get("include_context", [])

        # Build context from pipeline_data
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        context_parts = [
            f"Room: {trigger.room_name or 'Unknown'}",
            f"Current time: {now_str}",
        ]

        # Include requested pipeline data keys
        for key in include_context:
            value = pipeline_data.get(key)
            if value is not None:
                if isinstance(value, list):
                    if key == "person_detections":
                        persons = [
                            f"{d['name']} (confidence: {d['confidence']:.0%})"
                            for d in value
                        ]
                        context_parts.append(f"Persons detected: {', '.join(persons)}")
                    else:
                        context_parts.append(f"{key}: {json.dumps(value)}")
                elif isinstance(value, dict):
                    context_parts.append(f"{key}: {json.dumps(value)}")
                else:
                    context_parts.append(f"{key}: {value}")

        # If no explicit include_context, auto-include common keys
        if not include_context:
            if pipeline_data.get("person_detections"):
                persons = [
                    f"{d['name']} (confidence: {d['confidence']:.0%})"
                    for d in pipeline_data["person_detections"]
                ]
                context_parts.append(f"Persons detected: {', '.join(persons)}")
            if pipeline_data.get("vision_response"):
                context_parts.append(
                    f"Vision analysis: {pipeline_data['vision_response']}"
                )

        # Resolve response format instruction
        response_format = config.get("response_format", "default")
        if response_format == "custom":
            format_instruction = config.get(
                "response_schema", RESPONSE_FORMAT_TEMPLATES["default"]
            )
        else:
            format_instruction = RESPONSE_FORMAT_TEMPLATES.get(
                response_format, RESPONSE_FORMAT_TEMPLATES["default"]
            )

        context_prompt = (
            "\n".join(context_parts)
            + f"\n\n{prompt}\n\n"
            + format_instruction
        )

        raw_response = await self._logic.call(prompt=context_prompt)

        # Parse JSON response
        logic_data: dict = {}
        try:
            logic_data = json.loads(raw_response) if raw_response else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "logic_parse_failed",
                rule=execution.rule.name,
                raw=raw_response[:200] if raw_response else "",
            )
            logic_data = {
                "is_notification_needed": True,
                "user_notification": raw_response or "",
                "raw_response": raw_response,
            }

        result_data = {"logic_response": logic_data}

        # Check if notification is needed — if not, pipeline can still continue
        # (downstream steps might want to use the logic output)
        if not logic_data.get("is_notification_needed", True):
            result_data["notification_suppressed"] = True

        return StepResult(data=result_data)

    async def _step_translation(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Translate text to the target language."""
        if not self._translation:
            return StepResult(data={"translation": ""})

        config = step.config_json or {}

        # Determine the text to translate
        source_text = (
            pipeline_data.get("logic_response", {}).get("user_notification", "")
            or pipeline_data.get("vision_response", "")
        )
        if not source_text:
            return StepResult(data={"translation": ""})

        target_lang = config.get("target_language", "")
        prompt = source_text
        if target_lang:
            prompt = f"Translate the following to {target_lang}:\n\n{source_text}"

        translated = await self._translation.call(prompt=prompt)
        return StepResult(data={"translation": translated})

    async def _step_notification(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Dispatch notification to configured channels."""
        if not self._notifier:
            return StepResult(data={"notification_dispatched": False})

        # Don't notify if logic step suppressed it
        if pipeline_data.get("notification_suppressed"):
            return StepResult(data={"notification_dispatched": False})

        config = step.config_json or {}
        alert_level = config.get("alert_level", "warning")
        channels = config.get("channels", [])
        message_template = config.get("message_template", "")

        # Determine message
        message = (
            pipeline_data.get("translation")
            or pipeline_data.get("logic_response", {}).get("user_notification", "")
            or pipeline_data.get("vision_response", "")
        )
        if message_template:
            try:
                message = message_template.format(
                    message=message,
                    room=trigger.room_name or "",
                    **pipeline_data,
                )
            except (KeyError, IndexError):
                pass  # use the unformatted message

        eink_targets = config.get("eink_targets")
        rule_config = {}
        if channels:
            rule_config["channels"] = channels
        if eink_targets:
            rule_config["eink_targets"] = eink_targets
        results = await self._notifier.dispatch(
            alert_level=alert_level,
            message=message,
            room_name=trigger.room_name or "Unknown",
            rule_config=rule_config if rule_config else None,
        )

        return StepResult(
            data={
                "notification_dispatched": True,
                "notification_channels": results,
            }
        )

    async def _step_ha_action(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Call a Home Assistant service."""
        if not self._ha or not self._ha.configured:
            return StepResult(
                success=False,
                data={"ha_action": {"error": "Home Assistant not configured"}},
            )

        config = step.config_json or {}
        domain = config.get("domain", "")
        service = config.get("service", "")
        entity_id = config.get("entity_id", "")
        service_data = dict(config.get("data", {}))

        if not domain or not service:
            return StepResult(
                success=False,
                data={"ha_action": {"error": "Missing domain or service"}},
            )

        if entity_id:
            service_data["entity_id"] = entity_id

        await self._ha._call_service(domain, service, service_data)

        return StepResult(
            data={
                "ha_action": {
                    "domain": domain,
                    "service": service,
                    "entity_id": entity_id,
                    "success": True,
                }
            }
        )

    async def _step_activity_detection(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Record activities from pipeline data to the PersonActivity table.

        This is a pure *setter* step — it reads activity data produced by an
        upstream step (typically ``logic_reasoning`` with
        ``response_format: "activity_detection"``) and persists each activity
        via :pymethod:`PersonTrackingService.record_activity`.

        Config keys:
            source_key:         Pipeline data key to read from (default ``"logic_response"``).
            activities_path:    Key within the source object containing the
                                activity list (default ``"activities"``).
            default_confidence: Fallback confidence when not provided per
                                activity (default ``0.8``).
        """
        config = step.config_json or {}

        # Backward compatibility: warn if old-style config detected
        if "prompt" in config and "source_key" not in config:
            logger.warning(
                "activity_detection_deprecated_config",
                hint="activity_detection no longer runs LLM prompts; "
                     "use a preceding logic_reasoning step with "
                     "response_format='activity_detection' instead",
            )
            return StepResult(data={"detected_activities": []})

        source_key = config.get("source_key", "logic_response")
        activities_path = config.get("activities_path", "activities")
        default_confidence = config.get("default_confidence", 0.8)

        # Extract activities from pipeline data
        source_data = pipeline_data.get(source_key)
        if not source_data or not isinstance(source_data, dict):
            logger.info("activity_detection_no_source", source_key=source_key)
            return StepResult(data={"detected_activities": []})

        activities: list[dict] = source_data.get(activities_path, [])
        if not isinstance(activities, list):
            logger.warning(
                "activity_detection_bad_format",
                source_key=source_key,
                activities_path=activities_path,
            )
            return StepResult(data={"detected_activities": []})

        # Record each activity via person tracking
        if activities and self._person_tracking:
            for act in activities:
                try:
                    await self._person_tracking.record_activity(
                        person_id=act.get("person_id", "unknown"),
                        activity_type=act.get("activity_type", "unknown"),
                        room_name=trigger.room_name,
                        confidence=act.get("confidence", default_confidence),
                        source_event_id=execution.event_log_id,
                    )
                except Exception:
                    logger.warning("activity_record_failed", activity=act)

        return StepResult(data={"detected_activities": activities})

    async def _step_wait(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Pause the pipeline for a configured duration."""
        config = step.config_json or {}
        minutes = config.get("minutes", 5)
        resume_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

        return StepResult(
            data={"wait_started": datetime.now(timezone.utc).isoformat()},
            wait_until=resume_at,
        )

    async def _step_condition(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Evaluate a condition expression and branch accordingly."""
        config = step.config_json or {}
        expression = config.get("expression", "true")

        result = self._condition_eval.evaluate(expression, pipeline_data)

        next_step_id = (
            step.next_step_on_true if result else step.next_step_on_false
        )

        return StepResult(
            data={
                "condition": {
                    "expression": expression,
                    "result": result,
                    "branch": "true" if result else "false",
                }
            },
            next_step_id=next_step_id,
            # If no branch target and condition is false, stop pipeline
            should_continue=result if next_step_id is None else True,
        )

    async def _step_verification(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
    ) -> StepResult:
        """Verify whether household members completed specific activities.

        Queries the ``PersonActivity`` table to check each condition in the
        config.  No LLM calls are made — this is a pure database query step.

        Config keys:
            conditions:             List of activity conditions to check.
                Each condition has:
                - person_id (str): household member to check.
                - activity_type (str): activity to look for.
                - completed (bool): ``true`` to verify activity *was* done,
                  ``false`` to verify it was *not* done.  Default ``true``.
                - within_minutes (float|null): relative time window.
                - window_start (str|null): ISO-8601 UTC start for fixed window.
                - window_end (str|null): ISO-8601 UTC end for fixed window.
                - min_confidence (float): minimum confidence threshold (default 0.5).
            match_mode:             ``"all"`` (every condition must pass) or
                                    ``"any"`` (at least one must pass).
                                    Default ``"all"``.
            re_notify_if_failed:    Schedule retry on failure (default ``false``).
            re_notify_delay_minutes: Minutes before retry (default ``5``).
        """
        config = step.config_json or {}
        conditions = config.get("conditions", [])
        match_mode = config.get("match_mode", "all")
        re_notify_if_failed = config.get("re_notify_if_failed", False)
        re_notify_delay = config.get("re_notify_delay_minutes", 5)

        # Backward compatibility: warn if old-style config detected
        if "prompt" in config and not conditions:
            logger.warning(
                "verification_deprecated_config",
                hint="verification no longer runs LLM prompts; "
                     "configure activity conditions instead",
            )
            return StepResult(
                data={"verification": {"verified": False, "matched_conditions": [], "unmatched_conditions": []}},
                should_continue=False,
            )

        if not conditions:
            logger.info("verification_no_conditions")
            return StepResult(
                data={"verification": {"verified": False, "matched_conditions": [], "unmatched_conditions": []}},
                should_continue=False,
            )

        matched: list[dict] = []
        unmatched: list[dict] = []

        for cond in conditions:
            person_id = cond.get("person_id", "")
            activity_type = cond.get("activity_type", "")
            completed = cond.get("completed", True)
            within_minutes = cond.get("within_minutes")
            min_confidence = cond.get("min_confidence", 0.5)

            # Parse absolute window boundaries if provided
            window_start = None
            window_end = None
            if cond.get("window_start"):
                window_start = datetime.fromisoformat(cond["window_start"])
            if cond.get("window_end"):
                window_end = datetime.fromisoformat(cond["window_end"])

            activities: list[dict] = []
            if self._person_tracking:
                activities = await self._person_tracking.query_activities_in_window(
                    person_id=person_id,
                    activity_type=activity_type,
                    within_minutes=within_minutes,
                    window_start=window_start,
                    window_end=window_end,
                    min_confidence=min_confidence,
                )

            # Evaluate: completed=true passes if found, completed=false passes if NOT found
            found = len(activities) > 0
            passed = found if completed else not found

            entry = {
                "person_id": person_id,
                "activity_type": activity_type,
                "completed": completed,
                "found": found,
                "passed": passed,
                "activity_count": len(activities),
            }
            if passed:
                matched.append(entry)
            else:
                unmatched.append(entry)

        # Evaluate overall result
        if match_mode == "any":
            verified = len(matched) > 0
        else:  # "all"
            verified = len(unmatched) == 0

        result_data: dict = {
            "verification": {
                "verified": verified,
                "match_mode": match_mode,
                "matched_conditions": matched,
                "unmatched_conditions": unmatched,
            }
        }

        if not verified and re_notify_if_failed:
            resume_at = datetime.now(timezone.utc) + timedelta(minutes=re_notify_delay)
            return StepResult(
                data=result_data,
                wait_until=resume_at,
            )

        return StepResult(data=result_data, should_continue=verified)
