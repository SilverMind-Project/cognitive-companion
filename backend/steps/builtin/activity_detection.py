"""Activity detection step -- record activities to PersonActivity table."""

from __future__ import annotations

from backend.core.logging import get_logger
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
                "Record activities from pipeline data to the PersonActivity table. "
                "Reads from an upstream logic_reasoning step with "
                "response_format='activity_detection'."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "source_key": {
                        "type": "string",
                        "default": "logic_response",
                        "description": "Pipeline data key containing LLM output",
                    },
                    "activities_path": {
                        "type": "string",
                        "default": "activities",
                        "description": "Key within source object containing activity list",
                    },
                    "default_confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.8,
                    },
                },
            },
            default_config={
                "source_key": "logic_response",
                "activities_path": "activities",
                "default_confidence": 0.8,
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

        if activities and services.person_tracking:
            for act in activities:
                try:
                    await services.person_tracking.record_activity(
                        person_id=act.get("person_id", "unknown"),
                        activity_type=act.get("activity_type", "unknown"),
                        room_name=trigger.room_name,
                        confidence=act.get("confidence", default_confidence),
                        source_event_id=execution.event_log_id,
                    )
                except Exception:
                    logger.warning("activity_record_failed", activity=act)

        return StepResult(data={"detected_activities": activities})
