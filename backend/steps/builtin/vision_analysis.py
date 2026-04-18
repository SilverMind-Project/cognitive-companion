"""Vision analysis step -- run vision LLM on media.

Supports configurable image sources: the trigger media (default), additional
cameras (by sensor ID or room name), or both. Images can be filtered by
recency or time-of-day window.
"""

from __future__ import annotations

import json
from contextlib import suppress

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
class VisionAnalysisHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="vision_analysis",
            display_name="Vision Analysis (Deprecated)",
            category="perception",
            icon="mdi-eye-off",
            description=(
                "DEPRECATED: Use llm_call with model_id pointing to a vision "
                "model instead. This step will be removed in a future release."
            ),
            deprecated=True,
            config_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "default": "Describe what you see in this image.",
                    },
                    "use_annotated_image": {"type": "boolean", "default": False},
                    "image_source": {
                        "type": "string",
                        "enum": ["trigger", "additional", "both"],
                        "default": "trigger",
                        "description": (
                            "Which images to send to the vision model: "
                            "'trigger' = only the frames that triggered this pipeline, "
                            "'additional' = only extra cameras, "
                            "'both' = trigger frames plus additional."
                        ),
                    },
                    "max_images": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "description": "Maximum total images to send to the vision model.",
                    },
                    "additional_sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra camera sensor IDs to pull recent images from.",
                    },
                    "additional_room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pull images from all cameras in these rooms.",
                    },
                    "image_time_filter": {
                        "type": "object",
                        "properties": {
                            "since_minutes": {"type": "number"},
                            "time_start": {"type": "string", "description": "HH:MM"},
                            "time_end": {"type": "string", "description": "HH:MM"},
                        },
                        "description": "Time filter for additional images.",
                    },
                    "response_format": {
                        "type": "string",
                        "enum": ["default", "custom"],
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
                    "thinking": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Enable chain-of-thought reasoning. The model reasons inside "
                            "<think>…</think> tags; only the final answer is stored."
                        ),
                    },
                },
            },
            default_config={
                "prompt": "",
                "use_annotated_image": False,
                "image_source": "trigger",
                "max_images": 5,
                "additional_sensor_ids": [],
                "additional_room_names": [],
                "image_time_filter": {},
                "response_format": "default",
                "response_schema": "",
                "response_json_schema": "",
                "thinking": False,
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
        logger.warning(
            "vision_analysis_deprecated",
            rule=execution.rule.name,
            message=(
                "The vision_analysis step is deprecated. "
                "Migrate to llm_call with a vision model."
            ),
        )

        if not services.vision_provider:
            return StepResult(data={"vision_response": ""})

        config = step.config_json or {}
        raw_prompt = config.get("prompt", "Describe what you see in this image.")
        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }
        prompt = render_template(raw_prompt, pipeline_data, trigger_vars)

        # Resolve image source
        image_source = config.get("image_source", "trigger")
        max_images = config.get("max_images", 5)
        media_paths: list[str] = []

        if image_source in ("trigger", "both"):
            media_paths.extend(trigger.media_paths)

        if image_source in ("additional", "both") and services.event_aggregator:
            additional_sensors = config.get("additional_sensor_ids") or []
            additional_rooms = config.get("additional_room_names") or []
            time_filter = config.get("image_time_filter") or {}

            # Only query if there are filters to apply
            if additional_sensors or additional_rooms or image_source == "additional":
                extra = await services.event_aggregator.query_recent_media(
                    sensor_ids=additional_sensors if additional_sensors else None,
                    room_names=additional_rooms if additional_rooms else None,
                    limit=max_images,
                    since_minutes=time_filter.get("since_minutes"),
                    time_start=time_filter.get("time_start"),
                    time_end=time_filter.get("time_end"),
                )
                media_paths.extend(extra)

        # Limit total images sent to the model
        media_paths = media_paths[:max_images]

        # Resolve response format and schema for guided decoding
        response_format = config.get("response_format", "default")
        guided_schema: dict | None = None
        format_instruction = ""

        if response_format == "custom":
            format_instruction = config.get("response_schema", "")
            if format_instruction:
                prompt += f"\n\n{format_instruction}"
            raw_json_schema = config.get("response_json_schema", "")
            if raw_json_schema:
                with suppress(json.JSONDecodeError, TypeError):
                    guided_schema = json.loads(raw_json_schema)

        thinking: bool = bool(config.get("thinking", False))

        raw_temperature = config.get("temperature")
        raw_top_p = config.get("top_p")
        raw_max_tokens = config.get("max_tokens")
        temperature_override = float(raw_temperature) if raw_temperature is not None else None
        top_p_override = float(raw_top_p) if raw_top_p is not None else None
        max_tokens_override = int(raw_max_tokens) if raw_max_tokens is not None else None

        raw_response = await services.vision_provider.call(
            prompt=prompt,
            media_paths=media_paths,
            media_type=trigger.media_type,
            response_schema=guided_schema,
            thinking=thinking,
            temperature=temperature_override,
            top_p=top_p_override,
            max_tokens=max_tokens_override,
        )

        vision_data = raw_response
        if guided_schema:
            with suppress(json.JSONDecodeError, TypeError):
                vision_data = json.loads(raw_response) if raw_response else {}

        return StepResult(data={"vision_response": vision_data})
