"""Wait step -- pause pipeline for a configured duration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)


@StepRegistry.register
class WaitHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="wait",
            display_name="Wait",
            category="flow",
            icon="mdi-timer-sand",
            description="Pause the pipeline for a configured duration before continuing.",
            config_schema={
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "number",
                        "minimum": 0,
                        "default": 5,
                        "description": "Duration to wait in minutes",
                    },
                },
            },
            default_config={
                "minutes": 5,
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
        minutes = config.get("minutes", 5)
        resume_at = datetime.now(UTC) + timedelta(minutes=minutes)

        return StepResult(
            data={"wait_started": datetime.now(UTC).isoformat()},
            wait_until=resume_at,
        )
