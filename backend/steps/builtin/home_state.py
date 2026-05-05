"""home_state pipeline step: derive high-level home/away/asleep flags.

A thin wrapper around :class:`~backend.services.presence.PresenceService`
that emits simple boolean flags for use in ``condition`` steps or as
triggers for rules that react to home-state changes.

Result keys written to ``pipeline_data``
-----------------------------------------
For the configured ``output_key`` (default ``home``), the step writes:
``{output_key}_at_home`` (bool)
``{output_key}_asleep`` (bool)
``{output_key}_away`` (bool)
``{output_key}_state_unknown`` (bool)

These map directly to the four high-level home states:
- **at_home**: ``present_room``, ``present_home``, or ``asleep``
- **asleep**: ``asleep``
- **away**: ``away``
- **state_unknown**: ``unknown`` or ``stale``
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps._helpers import resolve_person_id
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


@StepRegistry.register
class HomeStateHandler(StepHandler):
    """Derive high-level home/away/asleep flags from presence service."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="home_state",
            display_name="Home State",
            category="perception",
            icon="mdi-home-variant",
            description=(
                "Derive simple home-state flags (at_home, asleep, away, "
                "state_unknown) from the fused presence service. Useful for "
                "condition steps that react to a person arriving home, leaving, "
                "or going to sleep."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": (
                            "Person to query. Leave blank to use the first "
                            "person found in pipeline_data."
                        ),
                    },
                    "output_key": {
                        "type": "string",
                        "default": "home",
                        "description": (
                            "pipeline_data key prefix. Emits "
                            "<key>_at_home, <key>_asleep, <key>_away, "
                            "<key>_state_unknown."
                        ),
                    },
                },
                "required": [],
            },
            default_config={
                "output_key": "home",
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
        person_id = resolve_person_id(config, pipeline_data)
        output_key = (config.get("output_key") or "home").strip() or "home"

        if not person_id or services.presence is None:
            return StepResult(
                data={
                    f"{output_key}_at_home": False,
                    f"{output_key}_asleep": False,
                    f"{output_key}_away": False,
                    f"{output_key}_state_unknown": True,
                },
            )

        snapshot = await services.presence.get(person_id)
        status = snapshot.status.value

        data: dict[str, Any] = {
            f"{output_key}_at_home": status in ("present_room", "present_home", "asleep"),
            f"{output_key}_asleep": status == "asleep",
            f"{output_key}_away": status == "away",
            f"{output_key}_state_unknown": status in ("unknown", "stale"),
        }
        return StepResult(data=data)
