"""Logic reasoning step -- run logic/reasoning LLM with structured output."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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

# ---------------------------------------------------------------------------
# Built-in JSON Schemas for structured output
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "is_notification_needed": {"type": "boolean"},
        "user_notification": {"type": "string"},
        "reasoning": {"type": "string"},
        "alert_level": {
            "type": "string",
            "enum": ["emergency", "warning", "info", "reminder"],
        },
    },
    "required": ["is_notification_needed", "user_notification", "reasoning"],
}

ACTIVITY_DETECTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "activities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "activity_type": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["activity_type"],
            },
        },
    },
    "required": ["activities"],
}

# Text instructions appended to the prompt alongside schema enforcement.
# These help the model understand intent even when guided decoding constrains output.
RESPONSE_FORMAT_TEMPLATES: dict[str, str] = {
    "default": (
        "Respond in JSON with keys: is_notification_needed (bool), "
        "user_notification (str), reasoning (str), alert_level (str: emergency|warning|info|reminder)"
    ),
    "activity_detection": (
        "Respond in JSON with keys: activities (list of objects with "
        "person_id, activity_type, confidence)"
    ),
}

# Map format names to their schemas for guided decoding
RESPONSE_FORMAT_SCHEMAS: dict[str, dict] = {
    "default": DEFAULT_SCHEMA,
    "activity_detection": ACTIVITY_DETECTION_SCHEMA,
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
                    "response_json_schema": {
                        "type": "string",
                        "description": (
                            "JSON Schema string for custom structured output. "
                            "Parsed and passed to the LLM for guided decoding. "
                            "Only used when response_format=custom."
                        ),
                    },
                },
            },
            default_config={
                "prompt": "",
                "include_context": [],
                "response_format": "default",
                "response_schema": "",
                "response_json_schema": "",
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
        raw_prompt = config.get("prompt", "")
        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }
        prompt = render_template(raw_prompt, pipeline_data, trigger_vars)
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

        # Resolve response format and schema for guided decoding
        response_format = config.get("response_format", "default")
        guided_schema: dict | None = None

        if response_format == "custom":
            format_instruction = config.get(
                "response_schema", RESPONSE_FORMAT_TEMPLATES["default"]
            )
            # Parse custom JSON schema if provided
            raw_json_schema = config.get("response_json_schema", "")
            if raw_json_schema:
                try:
                    guided_schema = json.loads(raw_json_schema)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "custom_json_schema_parse_failed",
                        rule=execution.rule.name,
                        raw=raw_json_schema[:200],
                    )
        else:
            format_instruction = RESPONSE_FORMAT_TEMPLATES.get(
                response_format, RESPONSE_FORMAT_TEMPLATES["default"]
            )
            guided_schema = RESPONSE_FORMAT_SCHEMAS.get(response_format)

        context_prompt = (
            "\n".join(context_parts)
            + f"\n\n{prompt}\n\n"
            + format_instruction
        )

        raw_response = await services.logic_provider.call(
            prompt=context_prompt,
            response_schema=guided_schema,
        )

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
