"""Pipeline step to open (or reuse) an activity session.

Opens a new ActivitySession record via ActivitySessionService and writes
its ID into pipeline_data for downstream steps.

Idempotent: if an open session of the same type exists for the same
person, returns the existing session without creating a duplicate.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.person import ActivitySourceEnum
from backend.models.pipeline import PipelineStep, WorkflowExecution
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
class ActivitySessionStartHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="activity_session_start",
            display_name="Start Activity Session",
            category="action",
            icon="mdi-play",
            description=(
                "Open a duration-aware activity session for a person. "
                "Idempotent: reuses an existing open session of the same type. "
                "Stores timeout configuration for automatic stale-session cleanup. "
                "All string fields support {{template}} syntax resolved against "
                "pipeline_data and trigger context."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "activity_type": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Activity type (e.g. sleep, bathroom, meal_prep). "
                            "Supports {{template}} syntax."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Person to attribute this session to. "
                            "Supports {{template}} syntax (e.g. {{person_detections.0.person_id}})."
                        ),
                    },
                    "room_name": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Room where the activity occurs. "
                            "Supports {{template}} syntax. Defaults to trigger room."
                        ),
                    },
                    "confidence": {
                        "type": ["number", "string"],
                        "default": 0.85,
                        "description": (
                            "Detection confidence (0-1). Accepts a fixed number "
                            "or {{template}} syntax."
                        ),
                    },
                    "source": {
                        "type": "string",
                        "enum": [s.value for s in ActivitySourceEnum],
                        "default": ActivitySourceEnum.vision_inferred.value,
                        "description": (
                            "How this session was determined. Drives how the "
                            "companion phrases answers about it: only "
                            "'guided_companion' supports claiming she completed "
                            "an action, the rest support 'she appeared to'."
                        ),
                    },
                    "timeout_minutes": {
                        "type": ["integer", "string"],
                        "default": "",
                        "description": (
                            "Maximum session duration in minutes before auto-close. "
                            "Uses built-in default for the activity type when empty. "
                            "Supports {{template}} syntax."
                        ),
                    },
                    "metadata_extra": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Optional JSON string of extra fields to merge into "
                            "session metadata_json. Supports {{template}} syntax."
                        ),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "session",
                        "description": (
                            "pipeline_data key to write the session result under. "
                            "Defaults to 'session'."
                        ),
                    },
                },
                "required": ["activity_type"],
            },
            default_config={
                "activity_type": "",
                "person_id": "",
                "room_name": "",
                "confidence": 0.85,
                "source": ActivitySourceEnum.vision_inferred.value,
                "timeout_minutes": "",
                "metadata_extra": "",
                "output_key": "session",
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

        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }

        activity_type = (
            render_template(config.get("activity_type", ""), pipeline_data, trigger_vars).strip()
            or "other"
        )

        person_id = (
            render_template(config.get("person_id", ""), pipeline_data, trigger_vars).strip()
            or "unknown"
        )

        room_name_tpl = config.get("room_name", "")
        room_name = (
            render_template(room_name_tpl, pipeline_data, trigger_vars).strip()
            or trigger.room_name
            or "unknown"
        )

        confidence_raw = config.get("confidence", 0.85)
        if isinstance(confidence_raw, str):
            resolved = render_template(confidence_raw, pipeline_data, trigger_vars).strip()
            try:
                confidence = max(0.0, min(1.0, float(resolved)))
            except ValueError, TypeError:
                logger.warning("session_start_bad_confidence", raw=confidence_raw)
                confidence = 0.85
        else:
            confidence = max(0.0, min(1.0, float(confidence_raw or 0.85)))

        source = (
            render_template(
                str(config.get("source", "") or ""), pipeline_data, trigger_vars
            ).strip()
            or ActivitySourceEnum.vision_inferred.value
        )

        timeout_raw = config.get("timeout_minutes", "")
        timeout_minutes = None
        if timeout_raw:
            tpl_resolved = render_template(str(timeout_raw), pipeline_data, trigger_vars).strip()
            try:
                timeout_minutes = int(tpl_resolved)
            except ValueError, TypeError:
                logger.warning("session_start_bad_timeout", raw=timeout_raw)

        metadata_extra_tpl = config.get("metadata_extra", "").strip()
        metadata: dict = {}
        if metadata_extra_tpl:
            rendered = render_template(metadata_extra_tpl, pipeline_data, trigger_vars)
            try:
                import json

                extra = json.loads(rendered)
                if isinstance(extra, dict):
                    metadata.update(extra)
            except json.JSONDecodeError, ValueError:
                logger.warning("session_start_metadata_extra_invalid", rendered=rendered[:120])

        output_key = (config.get("output_key", "session") or "session").strip() or "session"

        if services.activity:
            try:
                result = services.activity.open_session(
                    person_id=person_id,
                    activity_type=activity_type,
                    room_name=room_name,
                    confidence=confidence,
                    started_at=datetime.now(UTC),
                    start_event_id=execution.event_log_id,
                    source=source,
                    timeout_minutes=timeout_minutes,
                    metadata=metadata or None,
                )
            except Exception:
                logger.exception(
                    "session_start_error",
                    person_id=person_id,
                    activity_type=activity_type,
                )
                return StepResult(
                    success=False,
                    data={output_key: {"error": "failed to open activity session"}},
                )
        else:
            logger.warning(
                "session_start_no_service",
                person_id=person_id,
                activity_type=activity_type,
            )
            return StepResult(
                data={output_key: {"error": "activity session service not available"}}
            )

        session_data = {
            "session_id": result.session_id,
            "person_id": result.person_id,
            "activity_type": result.activity_type,
            "room_name": result.room_name,
            "started_at": result.opened_at.isoformat() if result.opened_at else None,
            "timeout_minutes": result.timeout_minutes,
            "source": result.source,
            "confidence": result.confidence,
            "was_existing": result.was_existing,
        }

        logger.info(
            "session_start_result",
            session_id=result.session_id,
            was_existing=result.was_existing,
            person_id=person_id,
            activity_type=activity_type,
        )

        return StepResult(data={output_key: session_data})
