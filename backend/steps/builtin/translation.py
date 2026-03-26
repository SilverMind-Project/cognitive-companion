"""Translation step -- translate text to target language."""

from __future__ import annotations

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
class TranslationHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="translation",
            display_name="Translation",
            category="action",
            icon="mdi-translate",
            description="Translate text to a target language using the translation LLM.",
            config_schema={
                "type": "object",
                "properties": {
                    "target_language": {
                        "type": "string",
                        "description": "Target language code or name (e.g. 'es', 'Tamil')",
                    },
                },
            },
            default_config={
                "target_language": "",
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
        if not services.translation_provider:
            return StepResult(data={"translation": ""})

        config = step.config_json or {}

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

        translated = await services.translation_provider.call(prompt=prompt)
        return StepResult(data={"translation": translated})
