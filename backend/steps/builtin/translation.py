"""Translation step -- translate text to target language."""

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
                    "source_text": {
                        "type": "string",
                        "description": (
                            "Text to translate. Supports {{variable}} templates. "
                            "Leave empty to auto-detect from logic_response.user_notification "
                            "or vision_response."
                        ),
                    },
                    "special_instructions": {
                        "type": "string",
                        "description": "Optional instructions to pre-pend to the prompt.",
                    },
                    "hallucination_marker": {
                        "type": "string",
                        "description": "Marker used to detect garbage responses and trigger retries.",
                    },
                },
            },
            default_config={
                "target_language": "ta",
                "source_text": "",
                "special_instructions": "Translate using informal Tanglish that is spoken in Chennai (i.e tamil mixed with English):  \n",
                "hallucination_marker": "",
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
        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }

        # Resolve source text: explicit template > logic_response > vision_response
        raw_source = config.get("source_text", "")
        if raw_source:
            source_text = render_template(raw_source, pipeline_data, trigger_vars)
        else:
            source_text = (
                pipeline_data.get("logic_response", {}).get("user_notification", "")
                or pipeline_data.get("vision_response", "")
            )
        if not source_text:
            return StepResult(data={"translation": ""})

        target_lang = config.get("target_language", "ta")
        prompt = source_text
        if target_lang:
            prompt = f"Translate the following to {target_lang}:\n\n{source_text}"

        special_instructions = config.get("special_instructions", "")
        if special_instructions:
            prompt = f"{special_instructions}\n{prompt}"

        h_marker = config.get("hallucination_marker", "")

        translated = await services.translation_provider.call(
            prompt=prompt,
            target_lang=target_lang,
            hallucination_marker=h_marker if h_marker else None,
        )
        return StepResult(data={"translation": translated})
