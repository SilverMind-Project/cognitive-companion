"""Activity detection step -- record a single activity to the PersonActivity table."""

from __future__ import annotations

from backend.core.logging import get_logger
from backend.core.template import render_template
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
class ActivityDetectionHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="activity_detection",
            display_name="Record Activity",
            category="state",
            icon="mdi-database-plus",
            description=(
                "Record a single activity to the PersonActivity table. "
                "All fields support {{template}} syntax resolved against pipeline_data "
                "and trigger context. Use multiple steps to record multiple activities."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "activity_type": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Activity type to record. Supports {{template}} syntax "
                            "(e.g. {{logic_response.activity_type}})."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Person to attribute this activity to. Supports {{template}} syntax "
                            "(e.g. {{person_detections.0.person_id}}). "
                            "Leave empty to record as unknown person."
                        ),
                    },
                    "confidence": {
                        "type": ["number", "string"],
                        "default": 0.8,
                        "description": (
                            "Confidence score (0-1). Accepts a fixed number or "
                            "{{template}} syntax (e.g. {{logic_response.confidence}})."
                        ),
                    },
                    "room_name": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Room where the activity occurred. Supports {{template}} syntax "
                            "(e.g. {{room_name}}). Defaults to the trigger room when empty."
                        ),
                    },
                    "trigger_cooloff": {
                        "type": "boolean",
                        "default": True,
                        "description": "If true, flags this rule for a rate-limit cool-off period after completion.",
                    },
                },
                "required": ["activity_type"],
            },
            default_config={
                "activity_type": "",
                "person_id": "",
                "confidence": 0.8,
                "room_name": "",
                "trigger_cooloff": True,
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

        activity_type = render_template(
            config.get("activity_type", ""), pipeline_data, trigger_vars
        ).strip()

        if not activity_type:
            logger.warning("activity_detection_missing_type", step_id=step.id)
            return StepResult(data={"detected_activities": []})

        person_id = render_template(
            config.get("person_id", ""), pipeline_data, trigger_vars
        ).strip() or "unknown"

        room_name_tpl = config.get("room_name", "")
        room_name = (
            render_template(room_name_tpl, pipeline_data, trigger_vars).strip()
            or trigger.room_name
        )

        confidence_raw = config.get("confidence", 0.8)
        if isinstance(confidence_raw, str):
            resolved = render_template(confidence_raw, pipeline_data, trigger_vars).strip()
            try:
                confidence = max(0.0, min(1.0, float(resolved)))
            except (ValueError, TypeError):
                logger.warning("activity_detection_bad_confidence", raw=confidence_raw)
                confidence = 0.8
        else:
            confidence = max(0.0, min(1.0, float(confidence_raw or 0.8)))

        if services.person_tracking:
            try:
                await services.person_tracking.record_activity(
                    person_id=person_id,
                    activity_type=activity_type,
                    room_name=room_name,
                    confidence=confidence,
                    source_event_id=execution.event_log_id,
                )
            except Exception:
                logger.warning(
                    "activity_record_failed",
                    person_id=person_id,
                    activity_type=activity_type,
                )

        result_data = {
            "detected_activities": [
                {
                    "person_id": person_id,
                    "activity_type": activity_type,
                    "room_name": room_name,
                    "confidence": confidence,
                }
            ]
        }

        if config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True

        return StepResult(data=result_data)
