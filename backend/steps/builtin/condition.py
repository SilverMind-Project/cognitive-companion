"""Condition step -- evaluate expression and branch accordingly."""

from __future__ import annotations

import re

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.condition_evaluator import ConditionEvaluator
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

_condition_eval = ConditionEvaluator()
# Strip {{ }} wrappers so authors can write either form:
#   steps.foo.outputs.bar == "x"          (evaluator IDENT syntax)
#   {{steps.foo.outputs.bar}} == "x"      (template-style reference)
_TEMPLATE_REF_RE = re.compile(r"\{\{\s*([\w][\w.]*)\s*\}\}")


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
                            "comparisons, boolean operators, exists(), contains()."
                        ),
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
        expression = _TEMPLATE_REF_RE.sub(r"\1", expression)

        result = _condition_eval.evaluate(expression, pipeline_data)

        next_step_id = step.next_step_on_true if result else step.next_step_on_false

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
            next_step_id=next_step_id,
            should_continue=result if next_step_id is None else True,
        )
