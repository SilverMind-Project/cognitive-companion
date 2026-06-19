"""Default gate graph presets."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule


def build_default_vlm_gate(
    db: Session,
    *,
    name: str = "Default VLM Confirm Gate",
    done_description: str | None = None,
    model_id: str | None = None,
) -> Rule:
    """Builds a default single-VLM gate graph.

    Structure:
      media_window_poll(source=auto) ->
        llm_call(vision model, JSON {complete, confidence, reason}) ->
          gate_verdict(complete_if = steps.llm_call_1.outputs.complete and steps.llm_call_1.outputs.confidence >= 0.7)
    """
    rule = Rule(
        name=name,
        enabled=True,
        trigger_types=[],
    )
    db.add(rule)
    db.flush()  # to get rule.id

    # 1. media_window_poll step
    poll_step = PipelineStep(
        rule_id=rule.id,
        order=0,
        step_type="media_window_poll",
        label="media_poll_0",
        config_json={
            "source": "auto",
        },
        enabled=True,
    )
    db.add(poll_step)

    # 2. llm_call step
    desc = done_description or "the resident has completed the current routine step"
    prompt = (
        "You are checking whether a guided-care routine step appears complete. "
        "Use only visible evidence from the image sequence. "
        f"The step is complete if: {desc}. "
        'Respond with strict JSON: {"complete": bool, "confidence": 0..1, "reason": "..."}'
    )

    response_json_schema = {
        "type": "object",
        "properties": {
            "complete": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
        },
        "required": ["complete", "confidence", "reason"],
        "additionalProperties": False,
    }

    llm_config = {
        "prompt": prompt,
        "image_source": "pipeline",
        "pipeline_image_path": "steps.media_poll_0.outputs.images",
        "response_format": "json_schema",
        "response_json_schema": json_schema_str(response_json_schema),
        "output_key": "vision_response",
        "temperature": 0.0,
        "use_profile_model": True,
    }
    if model_id is not None:
        llm_config["model_id"] = model_id

    llm_step = PipelineStep(
        rule_id=rule.id,
        order=1,
        step_type="llm_call",
        label="llm_call_1",
        config_json=llm_config,
        enabled=True,
    )
    db.add(llm_step)

    # 3. gate_verdict step
    verdict_step = PipelineStep(
        rule_id=rule.id,
        order=2,
        step_type="gate_verdict",
        label="gate_verdict_2",
        config_json={
            "complete_if": "steps.llm_call_1.outputs.vision_response.complete and steps.llm_call_1.outputs.vision_response.confidence >= 0.7",
            "confidence_path": "steps.llm_call_1.outputs.vision_response.confidence",
            "reason_path": "steps.llm_call_1.outputs.vision_response.reason",
        },
        enabled=True,
    )
    db.add(verdict_step)
    db.flush()

    # Connect edges
    edge1 = PipelineEdge(
        rule_id=rule.id,
        source_step_id=poll_step.id,
        source_port="main",
        target_step_id=llm_step.id,
        target_port="main",
    )
    edge2 = PipelineEdge(
        rule_id=rule.id,
        source_step_id=llm_step.id,
        source_port="main",
        target_step_id=verdict_step.id,
        target_port="main",
    )
    db.add(edge1)
    db.add(edge2)
    db.flush()

    return rule


def json_schema_str(schema: dict[str, Any]) -> str:
    import json

    return json.dumps(schema)
