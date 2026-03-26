"""Logic reasoning step -- run logic/reasoning LLM."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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


@StepRegistry.register
class LogicReasoningHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="logic_reasoning",
            display_name="Logic Reasoning",
            category="reasoning",
            icon="mdi-head-cog",
            description="Run logic/reasoning LLM to analyze context and make decisions.",
            config_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "default": ""},
                    "include_context": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pipeline data keys to include as context",
                    },
                    "response_format": {
                        "type": "string",
                        "enum": ["default", "activity_detection", "custom"],
                        "default": "default",
                    },
                    "response_schema": {
                        "type": "string",
                        "description": "Custom response schema instruction (when response_format=custom)",
                    },
                },
            },
            default_config={
                "prompt": "",
                "include_context": [],
                "response_format": "default",
                "response_schema": "",
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
        if not services.logic_provider:
            return StepResult(data={"logic_response": {}})

        config = step.config_json or {}
        prompt = config.get("prompt", "")
        include_context = config.get("include_context", [])

        # Build context from pipeline_data
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
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
                        context_parts.append(
                            f"Persons detected: {', '.join(persons)}"
                        )
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

        raw_response = await services.logic_provider.call(prompt=context_prompt)

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

        if not logic_data.get("is_notification_needed", True):
            result_data["notification_suppressed"] = True

        return StepResult(data=result_data)
