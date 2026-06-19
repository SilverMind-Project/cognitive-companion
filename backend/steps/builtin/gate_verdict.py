"""Verdict step -- evaluate condition expression and extract confidence/reason for gate validation.

This step is the required sink for any gate graph.
"""

from __future__ import annotations

import re

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.template import evaluate_condition
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.guided_task._verdict_utils import _bounded_float
from backend.services.pipeline_data_manager import resolve_pipeline_value
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

# Strip {{ }} wrappers for backward compatibility, same as condition.py
_TEMPLATE_REF_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")


@StepRegistry.register
class GateVerdictHandler(StepHandler):
    """The final sink for a gate graph rule. Evaluates the condition and extracts confidence and reason."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        try:
            default_min_conf = settings.as_float("guided_task.vision.confirm.min_confidence")
        except Exception:  # noqa: BLE001
            default_min_conf = 0.7
        return StepMetadata(
            type_name="gate_verdict",
            display_name="Gate Verdict",
            category="flow",
            icon="mdi-check-decagram",
            description="The final sink step of a gate graph. Sets the gate verdict complete, confidence, and reason.",
            gate_safe=True,
            gate_only=True,
            config_schema={
                "type": "object",
                "properties": {
                    "complete_if": {
                        "type": "string",
                        "description": (
                            "Expression evaluated at runtime. Truthy -> complete=True. "
                            "Supports Lark-based template grammar."
                        ),
                    },
                    "confidence_path": {
                        "type": "string",
                        "description": "Dotted or JMESPath path to the float confidence value (0..1).",
                    },
                    "reason_path": {
                        "type": "string",
                        "description": "Dotted or JMESPath path to the string reason value.",
                    },
                    "min_confidence": {
                        "type": "number",
                        "default": default_min_conf,
                        "description": "If complete is True, but confidence is below this value, the verdict is forced to False.",
                    },
                },
                "required": ["complete_if"],
            },
            default_config={
                "complete_if": "",
                "confidence_path": "",
                "reason_path": "",
                "min_confidence": default_min_conf,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "gate_verdict": {
                        "type": "object",
                        "properties": {
                            "complete": {"type": "boolean"},
                            "confidence": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["complete", "confidence", "reason"],
                    }
                },
                "required": ["gate_verdict"],
            },
            output_ports=("main",),
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
        complete_if = config.get("complete_if", "false")
        confidence_path = config.get("confidence_path", "")
        reason_path = config.get("reason_path", "")

        # Resolve the fail-closed confidence threshold. Precedence: the node's own
        # ``min_confidence`` config, then the runner profile's ``min_confidence``
        # (injected as ``pipeline_data["_profile"]``, the same inheritance path as
        # window_s/max_frames), then the ``config/settings.yaml`` global. Inheriting
        # the profile keeps the documented ``completion_gate.vision.*.min_confidence``
        # override live in one place (D22/D23) rather than dead in the runner.
        try:
            default_min_conf = settings.as_float("guided_task.vision.confirm.min_confidence")
        except Exception:  # noqa: BLE001
            default_min_conf = 0.7
        min_confidence = config.get("min_confidence")
        if min_confidence is None:
            profile_min = (pipeline_data.get("_profile") or {}).get("min_confidence")
            min_confidence = (
                _bounded_float(profile_min) if profile_min is not None else default_min_conf
            )
        else:
            min_confidence = _bounded_float(min_confidence)

        # 1. Evaluate complete_if expression
        complete = False
        try:
            expr = _TEMPLATE_REF_RE.sub(r"\1", complete_if)
            complete = evaluate_condition(expr, pipeline_data)
        except Exception as e:  # noqa: BLE001
            logger.error(
                "gate_verdict_eval_failed",
                error=str(e),
                complete_if=complete_if,
            )
            complete = False

        # 2. Resolve confidence
        confidence = 0.0
        if confidence_path:
            try:
                raw_conf = resolve_pipeline_value(pipeline_data, confidence_path)
                confidence = _bounded_float(raw_conf)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "gate_verdict_confidence_resolve_failed", error=str(e), path=confidence_path
                )
                confidence = 0.0
        else:
            confidence = 0.0

        # 3. Resolve reason
        reason = "gate_verdict"
        if reason_path:
            try:
                raw_reason = resolve_pipeline_value(pipeline_data, reason_path)
                if raw_reason is not None:
                    reason = str(raw_reason)
            except Exception as e:  # noqa: BLE001
                logger.warning("gate_verdict_reason_resolve_failed", error=str(e), path=reason_path)

        # 4. Enforce min_confidence if complete is True (fail-closed)
        if complete and confidence < min_confidence:
            logger.info(
                "gate_verdict_low_confidence_fail_closed",
                confidence=confidence,
                min_confidence=min_confidence,
                reason=reason,
            )
            complete = False
            reason = "low_confidence"

        result_data = {
            "gate_verdict": {
                "complete": complete,
                "confidence": confidence,
                "reason": reason,
            }
        }

        return StepResult(
            data=result_data,
            output_ports=("main",),
            should_continue=True,
        )
