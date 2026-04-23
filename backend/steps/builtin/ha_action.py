"""Home Assistant action step -- call HA services."""

from __future__ import annotations

from backend.core.template import render_template
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
            description="Call a Home Assistant service (light, switch, script, etc.). All string fields support {{variable}} template syntax.",
            config_schema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "HA domain (e.g. light, switch, script). Supports {{variable}} syntax.",
                    },
                    "service": {
                        "type": "string",
                        "description": "HA service (e.g. turn_on, toggle). Supports {{variable}} syntax.",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "HA entity ID (e.g. light.living_room). Supports {{variable}} syntax.",
                    },
                    "data": {
                        "type": "object",
                        "description": "Additional service data as JSON. String values support {{variable}} syntax.",
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

        trigger_vars = {
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }

        domain = render_template(config.get("domain", ""), pipeline_data, trigger_vars).strip()
        service = render_template(config.get("service", ""), pipeline_data, trigger_vars).strip()
        entity_id = render_template(config.get("entity_id", ""), pipeline_data, trigger_vars).strip()

        # Resolve template expressions in string values of the data dict
        raw_data = config.get("data", {}) or {}
        service_data: dict = {}
        for k, v in raw_data.items():
            if isinstance(v, str):
                service_data[k] = render_template(v, pipeline_data, trigger_vars)
            else:
                service_data[k] = v

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
