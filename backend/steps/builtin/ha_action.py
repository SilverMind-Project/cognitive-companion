"""Home Assistant action step -- call HA services."""

from __future__ import annotations

from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)


@StepRegistry.register
class HAActionHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="ha_action",
            display_name="HA Action",
            category="action",
            icon="mdi-home-automation",
            description="Call a Home Assistant service (light, switch, script, etc.).",
            config_schema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "HA domain (e.g. light, switch, script)",
                    },
                    "service": {
                        "type": "string",
                        "description": "HA service (e.g. turn_on, toggle)",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "HA entity ID (e.g. light.living_room)",
                    },
                    "data": {
                        "type": "object",
                        "description": "Additional service data as JSON",
                    },
                    "trigger_cooloff": {
                        "type": "boolean",
                        "default": True,
                        "description": "If true, flags this rule for a rate-limit cool-off period after completion.",
                    },
                },
                "required": ["domain", "service"],
            },
            default_config={
                "domain": "",
                "service": "",
                "entity_id": "",
                "data": {},
                "trigger_cooloff": True,
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
        if not services.ha_client or not services.ha_client.configured:
            return StepResult(
                success=False,
                data={"ha_action": {"error": "Home Assistant not configured"}},
            )

        config = step.config_json or {}
        domain = config.get("domain", "")
        service = config.get("service", "")
        entity_id = config.get("entity_id", "")
        service_data = dict(config.get("data", {}))

        if not domain or not service:
            return StepResult(
                success=False,
                data={"ha_action": {"error": "Missing domain or service"}},
            )

        if entity_id:
            service_data["entity_id"] = entity_id

        await services.ha_client._call_service(domain, service, service_data)

        result_data: dict = {
            "ha_action": {
                "domain": domain,
                "service": service,
                "entity_id": entity_id,
                "success": True,
            }
        }

        if config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True

        return StepResult(data=result_data)
