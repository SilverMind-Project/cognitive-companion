"""Condition step -- evaluate expression and branch accordingly.

Uses the Lark-based expression evaluator from ``backend.core.template``
for parse-safe evaluation with typed error reporting.
"""

from __future__ import annotations

import re

from backend.core.template import evaluate_condition
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

# Strip {{ }} wrappers so authors can write either form:
#   steps.foo.outputs.bar == "x"          (bare expression)
#   {{ steps.foo.outputs.bar == "x" }}    (template-style wrapping)
_TEMPLATE_REF_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")


@StepRegistry.register
class ConditionHandler(StepHandler):
    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="condition",
            display_name="Condition",
            category="reasoning",
            icon="mdi-help-circle",
            description="Evaluate a condition expression and branch the pipeline.",
            config_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": (
                            "Expression evaluated at runtime. Supports path access, "
                            "comparisons, boolean operators, JMESPath pipes, and "
                            "built-in functions: exists(), contains(), icontains(), "
                            "length(), lower(), upper(), keys(), values()."
                        ),
                        "x-ui": {
                            "widget": "template-textarea",
                            "rows": 3,
                            "supports_template": True,
                        },
                    },
                    "trigger_cooloff": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, flags this rule for a rate-limit cool-off period if the condition evaluates to true.",
                    },
                },
            },
            default_config={
                "expression": "",
                "trigger_cooloff": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "result": {"type": "boolean"},
                    "branch": {"type": "string"},
                },
            },
            output_ports=("true", "false"),
            gate_safe=True,
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json
        expression = config.get("expression", "true")
        # Strip {{ }} wrappers for backward compat; evaluate_condition
        # expects the raw expression body.
        expression = _TEMPLATE_REF_RE.sub(r"\1", expression)

        result = evaluate_condition(expression, pipeline_data)

        activated_port = "true" if result else "false"

        result_data: dict = {
            "condition": {
                "expression": expression,
                "result": result,
                "branch": "true" if result else "false",
            }
        }

        if result and config.get("trigger_cooloff", False):
            result_data["_cooloff_triggered"] = True

        return StepResult(
            data=result_data,
            output_ports=(activated_port,),
            should_continue=True,
        )
