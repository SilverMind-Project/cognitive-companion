"""Default gate graph presets.

A gate graph is a callable ``Rule`` (``trigger_types == []``) whose steps/edges
form a vision-confirm cascade ending on exactly one ``gate_verdict`` sink (D21,
D22). This module is the single factory for the seeded preset library: the
presets, the VG5 backfill script, and the tests all build through these
functions (no duplicated graph construction).

Presets are the canonical examples of the cheap-first cascade and the
one-verdict-sink + join pattern (VG08, D26).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule

logger = get_logger(__name__)


def json_schema_str(schema: dict[str, Any]) -> str:
    return json.dumps(schema)


# Strict JSON contract every VLM node in a gate graph must answer with.
_VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "complete": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["complete", "confidence", "reason"],
    "additionalProperties": False,
}


class _VlmCallConfig(TypedDict, total=False):
    """Bounded config for an ``llm_call`` vision node in a gate graph."""

    prompt: str
    image_source: str
    pipeline_image_path: str
    response_format: str
    response_json_schema: str
    output_key: str
    temperature: float
    use_profile_model: bool
    model_id: str
    heavy: bool


class _VerdictConfig(TypedDict, total=False):
    """Bounded config for the ``gate_verdict`` sink node."""

    complete_if: str
    confidence_path: str
    reason_path: str
    min_confidence: float


def _vlm_call_config(
    *,
    poll_label: str,
    done_description: str,
    output_key: str = "vision_response",
    model_id: str | None = None,
    heavy: bool = False,
) -> _VlmCallConfig:
    """Build the ``llm_call`` config that reads poll frames and answers the
    strict vision JSON contract. ``heavy=True`` tags the node so the Watch
    profile can prune it (D24)."""
    prompt = (
        "You are checking whether a guided-care routine step appears complete. "
        "Use only visible evidence from the image sequence. "
        f"The step is complete if: {done_description}. "
        'Respond with strict JSON: {"complete": bool, "confidence": 0..1, "reason": "..."}'
    )
    config: _VlmCallConfig = {
        "prompt": prompt,
        "image_source": "pipeline",
        "pipeline_image_path": f"steps.{poll_label}.outputs.images",
        "response_format": "json_schema",
        "response_json_schema": json_schema_str(_VISION_RESPONSE_SCHEMA),
        "output_key": output_key,
        "temperature": 0.0,
        "use_profile_model": True,
    }
    if model_id is not None:
        config["model_id"] = model_id
    if heavy:
        config["heavy"] = True
    return config


def _verdict_config(
    *,
    complete_if: str,
    confidence_path: str = "",
    reason_path: str = "",
    min_confidence: float | None = None,
) -> _VerdictConfig:
    config: _VerdictConfig = {
        "complete_if": complete_if,
        "confidence_path": confidence_path,
        "reason_path": reason_path,
    }
    if min_confidence is not None:
        config["min_confidence"] = min_confidence
    return config


def _add_step(
    db: Session,
    rule: Rule,
    *,
    order: int,
    step_type: str,
    label: str,
    config: Mapping[str, Any],
    position_x: float = 0.0,
    position_y: float = 0.0,
) -> PipelineStep:
    # Accept any Mapping (incl. the typed _VlmCallConfig/_VerdictConfig builders)
    # and materialize a plain dict for the JSON column.
    step = PipelineStep(
        rule_id=rule.id,
        order=order,
        step_type=step_type,
        label=label,
        config_json=dict(config),
        enabled=True,
        position_x=position_x,
        position_y=position_y,
    )
    db.add(step)
    return step


def _connect(
    db: Session,
    rule: Rule,
    source: PipelineStep,
    target: PipelineStep,
    *,
    source_port: str = "main",
    target_port: str = "main",
) -> None:
    db.add(
        PipelineEdge(
            rule_id=rule.id,
            source_step_id=source.id,
            source_port=source_port,
            target_step_id=target.id,
            target_port=target_port,
        )
    )


def build_default_vlm_gate(
    db: Session,
    *,
    name: str = "Default VLM Confirm Gate",
    done_description: str | None = None,
    model_id: str | None = None,
) -> Rule:
    """Builds a default single-VLM gate graph (the ``generic_vlm_confirm`` preset).

    Structure::

        media_window_poll(source=auto) ->
          llm_call(vision model, JSON {complete, confidence, reason}) ->
            gate_verdict(complete = vlm.complete and vlm.confidence >= 0.7)
    """
    rule = Rule(name=name, enabled=True, trigger_types=[])
    db.add(rule)
    db.flush()  # to get rule.id

    desc = done_description or "the resident has completed the current routine step"

    poll = _add_step(
        db, rule, order=0, step_type="media_window_poll", label="media_poll_0",
        config={"source": "auto"}, position_x=0, position_y=0,
    )
    llm = _add_step(
        db, rule, order=1, step_type="llm_call", label="llm_call_1",
        config=_vlm_call_config(poll_label="media_poll_0", done_description=desc, model_id=model_id),
        position_x=320, position_y=0,
    )
    verdict = _add_step(
        db, rule, order=2, step_type="gate_verdict", label="gate_verdict_2",
        config=_verdict_config(
            # The threshold is the single ``min_confidence`` knob (inherited from the
            # runner profile, per-step/per-routine overridable); do not duplicate it
            # in the expression. The verdict node fails closed below it.
            complete_if="steps.llm_call_1.outputs.vision_response.complete",
            confidence_path="steps.llm_call_1.outputs.vision_response.confidence",
            reason_path="steps.llm_call_1.outputs.vision_response.reason",
        ),
        position_x=640, position_y=0,
    )
    db.flush()

    _connect(db, rule, poll, llm)
    _connect(db, rule, llm, verdict)
    db.flush()
    return rule


def build_kettle_on_hob_gate(db: Session, *, name: str = "Kettle on Hob Gate") -> Rule:
    """Cheap-first cascade: detect the kettle/hob cheaply, only invoke the heavy
    VLM when something is there, and join both branches into one verdict (D22).

    Structure::

        media_window_poll(auto) -> scene_analysis(YOLO+Florence) ->
          condition("kettle detected?")
            --true --> llm_call(heavy VLM) --\\
            --false-------------------------- >-- gate_verdict (join)

    On the false branch the heavy VLM is skipped; the verdict still runs (the
    join fires with one live parent) and its expression resolves False because
    the VLM output was never written: a cheap exit with no model call.
    """
    rule = Rule(name=name, enabled=True, trigger_types=[])
    db.add(rule)
    db.flush()

    poll = _add_step(
        db, rule, order=0, step_type="media_window_poll", label="media_poll_0",
        config={"source": "auto"}, position_x=0, position_y=0,
    )
    scene = _add_step(
        db, rule, order=1, step_type="scene_analysis", label="scene_analysis_1",
        config={
            "image_source": "pipeline",
            "pipeline_image_path": "steps.media_poll_0.outputs.images",
        },
        position_x=320, position_y=0,
    )
    cond = _add_step(
        db, rule, order=2, step_type="condition", label="kettle_detected",
        config={
            "expression": (
                "{{ steps.scene_analysis_1.outputs.scene_detections | "
                "length([?icontains(label, 'kettle')]) > 0 or "
                "icontains(steps.scene_analysis_1.outputs.scene_description, 'kettle') }}"
            ),
        },
        position_x=640, position_y=0,
    )
    llm = _add_step(
        db, rule, order=3, step_type="llm_call", label="llm_call_1",
        config=_vlm_call_config(
            poll_label="media_poll_0",
            done_description="the kettle is filled and placed on the hob",
            heavy=True,
        ),
        position_x=960, position_y=-120,
    )
    verdict = _add_step(
        db, rule, order=4, step_type="gate_verdict", label="gate_verdict_1",
        config=_verdict_config(
            # Single threshold via ``min_confidence`` (profile-inherited); not duplicated
            # here. On the cheap false branch the VLM output is never written, so this
            # path resolves False and the verdict fails closed with no model call.
            complete_if="steps.llm_call_1.outputs.vision_response.complete",
            confidence_path="steps.llm_call_1.outputs.vision_response.confidence",
            reason_path="steps.llm_call_1.outputs.vision_response.reason",
        ),
        position_x=1280, position_y=0,
    )
    db.flush()

    _connect(db, rule, poll, scene)
    _connect(db, rule, scene, cond)
    _connect(db, rule, cond, llm, source_port="true")
    _connect(db, rule, cond, verdict, source_port="false")
    _connect(db, rule, llm, verdict)
    db.flush()
    return rule


def build_person_at_sink_gate(db: Session, *, name: str = "Person at Sink Gate") -> Rule:
    """Cheap presence/zone gate with no model call.

    Structure::

        media_window_poll(auto) -> condition(frames captured) --true--> gate_verdict

    A starting template: the caregiver edits the condition to a real zone or
    detection check. The verdict is reached only on the true branch; the false
    branch leaves it unreached, which the runner reads fail-closed (complete =
    False), so ``min_confidence`` is relaxed to 0 (there is no model score).
    """
    rule = Rule(name=name, enabled=True, trigger_types=[])
    db.add(rule)
    db.flush()

    poll = _add_step(
        db, rule, order=0, step_type="media_window_poll", label="media_poll_0",
        config={"source": "auto"}, position_x=0, position_y=0,
    )
    cond = _add_step(
        db, rule, order=1, step_type="condition", label="person_present",
        config={"expression": "{{ steps.media_poll_0.outputs.count > 0 }}"},
        position_x=320, position_y=0,
    )
    verdict = _add_step(
        db, rule, order=2, step_type="gate_verdict", label="gate_verdict_1",
        config=_verdict_config(
            complete_if="{{ steps.media_poll_0.outputs.count > 0 }}",
            min_confidence=0.0,
        ),
        position_x=640, position_y=0,
    )
    db.flush()

    _connect(db, rule, poll, cond)
    _connect(db, rule, cond, verdict, source_port="true")
    db.flush()
    return rule


@dataclass(frozen=True)
class GatePreset:
    """A shareable, seedable gate-graph template (D26)."""

    key: str
    name: str
    description: str
    summary: str
    build: Callable[[Session, str], Rule]


# The seeded preset library. ``build`` takes (db, name) so the create-from-preset
# endpoint can stamp a caregiver-chosen name through the same factory.
GATE_PRESETS: tuple[GatePreset, ...] = (
    GatePreset(
        key="generic_vlm_confirm",
        name="Generic VLM Confirm",
        description="One heavy vision model answers 'is this step done?'. Good default.",
        summary="media_window_poll -> llm_call(vision) -> gate_verdict",
        build=lambda db, name: build_default_vlm_gate(db, name=name),
    ),
    GatePreset(
        key="kettle_on_hob",
        name="Kettle on Hob",
        description=(
            "Cheap-first cascade: detect the kettle, only run the heavy vision "
            "model when one is present (saves compute)."
        ),
        summary=(
            "media_window_poll -> scene_analysis -> condition "
            "--true--> llm_call(heavy) --> gate_verdict; --false--> gate_verdict"
        ),
        build=lambda db, name: build_kettle_on_hob_gate(db, name=name),
    ),
    GatePreset(
        key="person_at_sink",
        name="Person at Sink",
        description="Cheap presence/zone gate with no model call. Edit the condition to fit.",
        summary="media_window_poll -> condition(presence) -> gate_verdict",
        build=lambda db, name: build_person_at_sink_gate(db, name=name),
    ),
)

PRESETS_BY_KEY: dict[str, GatePreset] = {p.key: p for p in GATE_PRESETS}


def get_preset(key: str) -> GatePreset | None:
    return PRESETS_BY_KEY.get(key)


def list_presets() -> list[GatePreset]:
    return list(GATE_PRESETS)


def seed_presets(db: Session) -> list[Rule]:
    """Idempotently seed the preset library as callable rules.

    Idempotency is by rule name (``rules.name`` is unique); an existing preset
    is left untouched so caregiver edits to a seeded copy are never clobbered.
    """
    seeded: list[Rule] = []
    for preset in GATE_PRESETS:
        existing = db.query(Rule).filter(Rule.name == preset.name).first()
        if existing is not None:
            seeded.append(existing)
            continue
        rule = preset.build(db, preset.name)
        logger.info("gate_preset_seeded", preset_key=preset.key, rule_id=rule.id)
        seeded.append(rule)
    db.flush()
    return seeded
