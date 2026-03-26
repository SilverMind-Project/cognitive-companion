"""Condition step -- evaluate expression and branch accordingly."""

from __future__ import annotations

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
                },
            },
            default_config={
                "expression": "",
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
        expression = config.get("expression", "true")

        result = _condition_eval.evaluate(expression, pipeline_data)

        next_step_id = (
            step.next_step_on_true if result else step.next_step_on_false
        )

        return StepResult(
            data={
                "condition": {
                    "expression": expression,
                    "result": result,
                    "branch": "true" if result else "false",
                }
            },
            next_step_id=next_step_id,
            should_continue=result if next_step_id is None else True,
        )
