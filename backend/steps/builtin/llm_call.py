"""Unified LLM call step -- send a prompt to any configured model.

This step is the single LLM interface for the pipeline, handling vision
analysis, logic reasoning, and translation through a model-agnostic design.
The
specific model is selected per step via ``model_id``, which must match an
entry in ``llm.models`` in settings.yaml.

Key capabilities controlled by step config
------------------------------------------
* **Model selection** -- pick any named model from the registry.
* **Vision input** -- attach trigger frames or images from additional cameras.
* **Sensor-ordered image assembly** -- images grouped by sensor then
  sorted chronologically within each group; ideal for inter-frame analysis.
* **Structured output** -- optionally enforce a JSON Schema via guided
  decoding (vLLM) or prompt injection (other servers).
* **Translation helpers** -- ``special_instructions`` prepended to the
  prompt; ``hallucination_marker`` triggers tenacity retries.
* **Output key** -- result stored under a configurable pipeline_data key
  (defaults to ``llm_response``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.integrations.llm.json_utils import parse_llm_json
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps._image_utils import resolve_image_sources
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


@StepRegistry.register
class LLMCallHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="llm_call",
            display_name="LLM Call",
            category="reasoning",
            icon="mdi-brain",
            description=(
                "Send a prompt to any configured LLM model. "
                "Supports text, vision (camera images), JSON schema enforcement, "
                "and translation helpers."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "model_id": {
                        "type": "string",
                        "description": "ID of the model from llm.models in settings.yaml",
                    },
                    "prompt": {
                        "type": "string",
                        "default": "",
                        "description": "Prompt text. Supports {{variable}} templates.",
                    },
                    "include_context": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pipeline data keys to prepend as context.",
                    },
                    "image_source": {
                        "type": "string",
                        "enum": ["none", "trigger", "additional", "both"],
                        "default": "none",
                        "description": (
                            "'trigger' = frames that triggered this pipeline, "
                            "'additional' = extra cameras only, "
                            "'both' = trigger frames + additional cameras."
                        ),
                    },
                    "max_images": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "description": "Hard cap on total images sent to the model.",
                    },
                    "additional_sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Extra camera sensor IDs to pull images from. "
                            "Order determines the grouping order when "
                            "sort_by_sensor_then_time is enabled."
                        ),
                    },
                    "additional_room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pull images from all cameras in these rooms.",
                    },
                    "images_per_sensor": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "description": (
                            "Default maximum images per sensor. Used as the fallback "
                            "when sensor_frame_limits does not specify a sensor."
                        ),
                    },
                    "sensor_frame_limits": {
                        "type": "object",
                        "additionalProperties": {"type": "integer", "minimum": 1},
                        "description": (
                            "Per-camera frame limit overrides. Keys are sensor IDs, "
                            "values are the max recent frames for that sensor. "
                            "Sensors not listed here use images_per_sensor as the default."
                        ),
                    },
                    "sort_by_sensor_then_time": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true, images within each sensor group are sorted "
                            "oldest-first (chronological) for inter-frame analysis. "
                            "When false, images are newest-first. Does not gate "
                            "per-sensor limits or sensor-ordered assembly."
                        ),
                    },
                    "trigger_images_count": {
                        "type": "integer",
                        "minimum": 0,
                        "description": (
                            "Maximum trigger frames to include (most recent N). "
                            "0 or unset means all available trigger frames."
                        ),
                    },
                    "use_annotated_image": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true and pipeline_data contains an annotated_image "
                            "(base64 JPEG from person_identification), prepend it as "
                            "the first image in the media payload."
                        ),
                    },
                    "image_time_filter": {
                        "type": "object",
                        "properties": {
                            "since_minutes": {"type": "number"},
                            "time_start": {"type": "string"},
                            "time_end": {"type": "string"},
                        },
                        "description": "Time filter for additional camera images.",
                    },
                    "response_format": {
                        "type": "string",
                        "enum": ["text", "json_schema", "json_free"],
                        "default": "text",
                        "description": (
                            "'text' = free-form string output. "
                            "'json_schema' = enforce a JSON Schema (guided decoding "
                            "or prompt injection). "
                            "'json_free' = request JSON without a schema."
                        ),
                    },
                    "response_schema": {
                        "type": "string",
                        "description": (
                            "Natural-language description of the expected JSON format, "
                            "appended to the prompt. Used with any response_format."
                        ),
                    },
                    "response_json_schema": {
                        "type": "string",
                        "description": (
                            "JSON Schema string for structured output enforcement. "
                            "Parsed and passed to the provider. "
                            "Only used when response_format=json_schema."
                        ),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "llm_response",
                        "description": (
                            "Pipeline data key where the result is stored. "
                            "Use 'logic_response', 'vision_response', or 'translation' "
                            "for compatibility with downstream steps."
                        ),
                    },
                    "special_instructions": {
                        "type": "string",
                        "default": "",
                        "description": "Text prepended to the prompt (e.g. translation style guide).",
                    },
                    "hallucination_marker": {
                        "type": "string",
                        "default": "",
                        "description": "If found in the response, the call is retried automatically.",
                    },
                    "thinking": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Enable chain-of-thought reasoning. The model reasons inside "
                            "<think>…</think> tags; only the final answer is stored. "
                            "Only effective when the selected model supports thinking."
                        ),
                    },
                    "temperature": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 2.0,
                        "description": "Sampling temperature override. Leave blank to use the model default.",
                    },
                    "top_p": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Top-p (nucleus) sampling override. Leave blank to use the model default.",
                    },
                    "max_tokens": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Max tokens to generate override. Leave blank to use the model default.",
                    },
                },
                "required": ["model_id"],
            },
            default_config={
                "model_id": "",
                "prompt": "",
                "include_context": [],
                "image_source": "none",
                "max_images": 5,
                "additional_sensor_ids": [],
                "additional_room_names": [],
                "images_per_sensor": 3,
                "sensor_frame_limits": {},
                "sort_by_sensor_then_time": False,
                "trigger_images_count": 0,
                "use_annotated_image": False,
                "image_time_filter": {},
                "response_format": "text",
                "response_schema": "",
                "response_json_schema": "",
                "output_key": "llm_response",
                "special_instructions": "",
                "hallucination_marker": "",
                "thinking": False,
                "temperature": None,
                "top_p": None,
                "max_tokens": None,
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
        if not services.llm_model_registry:
            logger.warning("llm_call_no_registry", step=step.step_type)
            return StepResult(data={})

        config = step.config_json or {}
        model_id: str = config.get("model_id", "")
        if not model_id:
            logger.warning("llm_call_no_model_id", rule=execution.rule.name)
            return StepResult(data={})

        provider = services.llm_model_registry.get_provider(model_id)
        if provider is None:
            logger.error(
                "llm_call_unknown_model",
                model_id=model_id,
                rule=execution.rule.name,
            )
            return StepResult(data={})

        model_cfg = services.llm_model_registry.get_config(model_id)

        # -- Resolve prompt template ------------------------------------------
        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }
        raw_prompt: str = config.get("prompt", "")
        prompt = render_template(raw_prompt, pipeline_data, trigger_vars)

        # -- Apply special instructions ----------------------------------------
        special_instructions: str = config.get("special_instructions", "")
        if special_instructions:
            prompt = f"{special_instructions}\n{prompt}"

        # -- Build context block -----------------------------------------------
        include_context: list[str] = config.get("include_context", [])
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        context_parts = [
            f"Room: {trigger.room_name or 'Unknown'}",
            f"Current time: {now_str}",
        ]

        for key in include_context:
            from backend.services.pipeline_data_manager import resolve_pipeline_value
            value = resolve_pipeline_value(pipeline_data, key)
            if value is not None:
                if isinstance(value, list):
                    if key == "person_detections":
                        persons = [
                            f"{d['name']} (confidence: {d['confidence']:.0%})" for d in value
                        ]
                        context_parts.append(f"Persons detected: {', '.join(persons)}")
                    else:
                        context_parts.append(f"{key}: {json.dumps(value)}")
                elif isinstance(value, dict):
                    context_parts.append(f"{key}: {json.dumps(value)}")
                else:
                    context_parts.append(f"{key}: {value}")

        # Auto-include common keys when include_context is empty
        if not include_context:
            if pipeline_data.get("person_detections"):
                persons = [
                    f"{d['name']} (confidence: {d['confidence']:.0%})"
                    for d in pipeline_data["person_detections"]
                ]
                context_parts.append(f"Persons detected: {', '.join(persons)}")
            if pipeline_data.get("vision_response"):
                context_parts.append(f"Vision analysis: {pipeline_data['vision_response']}")

        context_block = "\n".join(context_parts)

        # -- Resolve response format / schema ----------------------------------
        response_format: str = config.get("response_format", "text")
        guided_schema: dict | None = None
        format_instruction = ""

        if response_format == "json_schema":
            raw_schema = config.get("response_json_schema", "")
            if raw_schema:
                parsed_schema = parse_llm_json(raw_schema)
                if isinstance(parsed_schema, dict):
                    guided_schema = parsed_schema
                else:
                    logger.warning(
                        "llm_call_schema_parse_failed",
                        model_id=model_id,
                        rule=execution.rule.name,
                    )
                    guided_schema = None
            format_instruction = config.get("response_schema", "")
            if not format_instruction and guided_schema:
                format_instruction = "Respond with valid JSON matching the provided schema."
        elif response_format == "json_free":
            format_instruction = config.get("response_schema", "Respond with valid JSON.")

        # Append format instruction to the prompt
        parts: list[str] = [context_block]
        if prompt:
            parts.append(prompt)
        if format_instruction:
            parts.append(format_instruction)
        full_prompt = "\n\n".join(p for p in parts if p)

        # -- Assemble images ---------------------------------------------------
        has_vision = model_cfg and "vision" in model_cfg.capabilities
        image_source: str = config.get("image_source", "none")

        if has_vision and image_source != "none":
            sort_by_sensor: bool = bool(config.get("sort_by_sensor_then_time", False))
            media_paths = await resolve_image_sources(
                config, trigger, services.event_aggregator,
                default_max_images=5,
                default_images_per_sensor=3,
                sort_by_sensor=sort_by_sensor,
            )
        else:
            media_paths: list[str] = []

        # -- Annotated image (from person_identification) ----------------------
        if config.get("use_annotated_image"):
            annotated = pipeline_data.get("annotated_image")
            if annotated:
                max_images = int(config.get("max_images", 5))
                media_paths.insert(0, f"data:image/jpeg;base64,{annotated}")
                media_paths = media_paths[:max_images]

        # -- Call the model ---------------------------------------------------
        hallucination_marker: str = config.get("hallucination_marker", "")
        thinking: bool = bool(config.get("thinking", False))

        # Sampling overrides: only pass if explicitly set in step config
        raw_temperature = config.get("temperature")
        raw_top_p = config.get("top_p")
        raw_max_tokens = config.get("max_tokens")
        temperature_override = float(raw_temperature) if raw_temperature is not None else None
        top_p_override = float(raw_top_p) if raw_top_p is not None else None
        max_tokens_override = int(raw_max_tokens) if raw_max_tokens is not None else None

        raw_response = await provider.call(
            prompt=full_prompt,
            media_paths=media_paths if media_paths else None,
            media_type=trigger.media_type if media_paths else None,
            response_schema=guided_schema,
            thinking=thinking,
            temperature=temperature_override,
            top_p=top_p_override,
            max_tokens=max_tokens_override,
            hallucination_marker=hallucination_marker if hallucination_marker else None,
        )

        # -- Parse output -----------------------------------------------------
        output_key: str = config.get("output_key", "llm_response") or "llm_response"
        result_value: str | dict | list = raw_response or ""

        if response_format in ("json_schema", "json_free") and raw_response:
            result_value = parse_llm_json(raw_response)

        if isinstance(result_value, str) and not result_value:
            logger.warning(
                "llm_call_empty_response",
                model_id=model_id,
                rule=execution.rule.name,
            )
        elif isinstance(result_value, str) and response_format in (
            "json_schema",
            "json_free",
        ):
            logger.warning(
                "llm_call_json_parse_failed",
                model_id=model_id,
                rule=execution.rule.name,
                raw=raw_response[:200] if raw_response else "",
            )

        result_data: dict = {output_key: result_value}

        # Propagate notification suppression when output mimics logic_response
        if (
            output_key == "logic_response"
            and isinstance(result_value, dict)
            and not result_value.get("is_notification_needed", True)
        ):
            result_data["notification_suppressed"] = True

        return StepResult(data=result_data)
