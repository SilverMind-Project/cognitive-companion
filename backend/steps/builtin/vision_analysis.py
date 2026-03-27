"""Vision analysis step -- run vision LLM on media."""

from __future__ import annotations

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


@StepRegistry.register
class VisionAnalysisHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="vision_analysis",
            display_name="Vision Analysis",
            category="perception",
            icon="mdi-eye",
            description="Run vision LLM analysis on camera frames or images.",
            config_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "default": "Describe what you see in this image.",
                    },
                    "use_annotated_image": {"type": "boolean", "default": False},
                },
            },
            default_config={
                "prompt": "",
                "use_annotated_image": False,
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
        if not services.vision_provider:
            return StepResult(data={"vision_response": ""})

        config = step.config_json or {}
        raw_prompt = config.get("prompt", "Describe what you see in this image.")
        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }
        prompt = render_template(raw_prompt, pipeline_data, trigger_vars)
        media_paths = trigger.media_paths

        vision_response = await services.vision_provider.call(
            prompt=prompt,
            media_paths=media_paths,
            media_type=trigger.media_type,
        )
        return StepResult(data={"vision_response": vision_response})
