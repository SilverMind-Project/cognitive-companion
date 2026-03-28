"""Notification step -- dispatch notifications to configured channels."""

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
class NotificationHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="notification",
            display_name="Notification",
            category="action",
            icon="mdi-bell",
            description="Dispatch notifications to configured channels (WebSocket, Telegram, eInk, TTS).",
            config_schema={
                "type": "object",
                "properties": {
                    "alert_level": {
                        "type": "string",
                        "enum": ["emergency", "warning", "info", "reminder"],
                        "default": "warning",
                    },
                    "channels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override default channels for this alert level",
                    },
                    "message_template": {
                        "type": "string",
                        "description": "Python format string with {message}, {room}, etc.",
                    },
                    "eink_targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sensor IDs of eink displays (empty = all)",
                    },
                    "ha_media_player": {
                        "type": "string",
                        "description": "HA media_player entity ID for TTS playback",
                    },
                },
            },
            default_config={
                "alert_level": "warning",
                "channels": [],
                "message_template": "",
                "eink_targets": [],
                "ha_media_player": "",
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
        if not services.notification_dispatcher:
            return StepResult(data={"notification_dispatched": False})

        # Don't notify if logic step suppressed it
        if pipeline_data.get("notification_suppressed"):
            return StepResult(data={"notification_dispatched": False})

        config = step.config_json or {}
        alert_level = config.get("alert_level", "warning")
        channels = config.get("channels", [])
        message_template = config.get("message_template", "")

        # Determine message
        message = (
            pipeline_data.get("translation")
            or pipeline_data.get("logic_response", {}).get("user_notification", "")
            or pipeline_data.get("vision_response", "")
        )
        if message_template:
            try:
                message = message_template.format(
                    message=message,
                    room=trigger.room_name or "",
                    **pipeline_data,
                )
            except (KeyError, IndexError):
                pass

        eink_targets = config.get("eink_targets")
        ha_media_player = config.get("ha_media_player")
        rule_config = {}
        if channels:
            rule_config["channels"] = channels
        if eink_targets:
            rule_config["eink_targets"] = eink_targets
        if ha_media_player:
            rule_config["ha_media_player"] = ha_media_player
        results = await services.notification_dispatcher.dispatch(
            alert_level=alert_level,
            message=message,
            room_name=trigger.room_name or "Unknown",
            rule_config=rule_config if rule_config else None,
        )

        return StepResult(
            data={
                "notification_dispatched": True,
                "notification_channels": results,
            }
        )
