"""Signal-emit step -- write a CC-local signal from a pipeline (DL-M06).

CC-local signals (kinds never produced by the CTS orchestrator, e.g.
``tea_intent_suspected``, ``inferred_dwell_exceeded``) are the label store for
shadow-mode detectors (DL10): a rule records a suspected event here, and the
caregiver's accurate/inaccurate feedback on the existing signals feed becomes
the precision dataset, with no new table and no new labeling UI.

This is a write step (``category="action"``); it is not ``gate_safe`` and must
never run inside a non-durable gate graph.
"""

from __future__ import annotations

from cts_contracts import DementiaSignalSeverity

from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.cts.signal_config import CC_LOCAL_SIGNAL_KINDS
from backend.steps import StepRegistry
from backend.steps._helpers import make_trigger_vars, resolve_person_id
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

_SEVERITIES: tuple[str, ...] = tuple(str(s) for s in DementiaSignalSeverity)


def _render_context(
    raw_context: dict,
    pipeline_data: dict,
    trigger_vars: dict[str, str],
) -> dict:
    """Render string values in *raw_context* through the template engine.

    Non-string values pass through unchanged (a rule may want a literal
    number or nested object in context, not just interpolated text).
    """
    rendered: dict = {}
    for key, value in raw_context.items():
        if isinstance(value, str):
            rendered[key] = render_template(value, pipeline_data, trigger_vars)
        else:
            rendered[key] = value
    return rendered


def _resolve_value(raw_value: object, pipeline_data: dict, trigger_vars: dict[str, str]) -> float:
    """Resolve the ``value`` config to a float.

    Accepts a literal number or a ``{{ }}`` template string (e.g. an
    upstream LLM's confidence). Falls back to ``1.0`` when unset or
    unresolvable, since ``DementiaSignal.value`` is a required column.
    """
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        return float(raw_value)
    if isinstance(raw_value, str) and raw_value.strip():
        rendered = render_template(raw_value, pipeline_data, trigger_vars).strip()
        try:
            return float(rendered)
        except ValueError:
            logger.warning("signal_emit_value_unresolvable", raw_value=raw_value)
            return 1.0
    return 1.0


@StepRegistry.register
class SignalEmitHandler(StepHandler):
    """Pipeline step that writes a CC-local signal via ``services.signals``."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="signal_emit",
            display_name="Emit Signal",
            category="action",
            icon="mdi-bell-alert-outline",
            description=(
                "Record a CC-local signal (e.g. a shadow-mode detector's suspected "
                "event) on the signals feed, so caregiver accurate/inaccurate "
                "feedback becomes a labeled precision dataset."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": list(CC_LOCAL_SIGNAL_KINDS),
                        "description": (
                            "CC-local signal kind. Never a CTS-produced kind "
                            "(e.g. fall_suspected) -- those are rejected."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "description": (
                            "Household member ID this signal is about. Falls back to "
                            "pipeline_data['persons'][0] / pipeline_data['person_id'] "
                            "when omitted (see resolve_person_id)."
                        ),
                    },
                    "severity": {
                        "type": "string",
                        "enum": list(_SEVERITIES),
                        "default": "info",
                    },
                    "value": {
                        "type": ["number", "string"],
                        "default": 1.0,
                        "description": (
                            "Numeric value for this signal, or a {{ }} template "
                            "resolving to one (e.g. an upstream llm_call confidence). "
                            "Defaults to 1.0 when unset or unresolvable."
                        ),
                    },
                    "context": {
                        "type": "object",
                        "default": {},
                        "description": (
                            "Freeform context, merged with {rule_id, execution_id} "
                            "provenance. String values support {{ }} templates."
                        ),
                    },
                    "dedupe_minutes": {
                        "type": "integer",
                        "default": 60,
                        "minimum": 0,
                        "description": (
                            "Skip the write if an unacknowledged signal of the same "
                            "kind and person exists within this window. 0 disables dedup."
                        ),
                    },
                    "trigger_cooloff": {
                        "type": "boolean",
                        "default": True,
                        "description": (
                            "If true and a signal was actually emitted (not deduped or "
                            "rejected), flags this rule for a rate-limit cool-off period "
                            "(the rule's cool_off_minutes). This is the intended way to "
                            "rate-limit a shadow detector: the rule's trigger stays "
                            "frequent, and only a real positive detection arms the pause."
                        ),
                    },
                },
                "required": ["kind"],
            },
            default_config={
                "kind": CC_LOCAL_SIGNAL_KINDS[0] if CC_LOCAL_SIGNAL_KINDS else "",
                "person_id": "",
                "severity": "info",
                "value": 1.0,
                "context": {},
                "dedupe_minutes": 60,
                "trigger_cooloff": True,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "emitted": {"type": "boolean"},
                    "reason": {"type": ["string", "null"]},
                    "signal_row_id": {"type": ["integer", "null"]},
                },
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
        kind = config.get("kind", "")

        # Defense in depth: config_schema's enum already rejects a forged kind
        # at bundle-import and step-config-save time (write-time JSONSchema
        # validation), but a hand-edited config_json row would bypass that.
        if kind not in CC_LOCAL_SIGNAL_KINDS:
            logger.warning("signal_emit_invalid_kind", kind=kind)
            return StepResult(
                success=False,
                data={"emitted": False, "reason": "invalid_kind", "signal_row_id": None},
            )

        if services.signals is None:
            logger.warning("signal_emit_service_unavailable", kind=kind)
            return StepResult(
                data={"emitted": False, "reason": "unavailable", "signal_row_id": None}
            )

        trigger_vars = make_trigger_vars(trigger)
        person_id = resolve_person_id(config, pipeline_data)
        if not person_id:
            logger.warning("signal_emit_no_person_id", kind=kind)
            return StepResult(
                success=False,
                data={"emitted": False, "reason": "no_person_id", "signal_row_id": None},
            )

        severity = config.get("severity") or "info"
        value = _resolve_value(config.get("value", 1.0), pipeline_data, trigger_vars)
        raw_context = config.get("context") or {}
        context = _render_context(raw_context, pipeline_data, trigger_vars)
        context["rule_id"] = execution.rule_id
        context["execution_id"] = execution.id

        result = await services.signals.emit(
            signal_kind=kind,
            person_id=person_id,
            severity=severity,
            value=value,
            context=context,
            dedupe_minutes=int(config.get("dedupe_minutes", 60)),
        )

        logger.info(
            "signal_emit_done",
            kind=kind,
            person_id=person_id,
            emitted=result["emitted"],
            reason=result["reason"],
        )

        result_data = dict(result)
        if result["emitted"] and config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True

        return StepResult(data=result_data)
