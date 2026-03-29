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


def _format_channel_message(
    template: str,
    base_message: str,
    trigger: TriggerContext,
    pipeline_data: dict,
) -> str:
    """Render a channel-specific template, falling back to *base_message*."""
    if not template:
        return base_message
    try:
        return template.format(
            message=base_message,
            room=trigger.room_name or "",
            **pipeline_data,
        )
    except (KeyError, IndexError, ValueError):
        return base_message


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
                        "description": "Default template with {message}, {room}, etc.",
                    },
                    "telegram_template": {
                        "type": "string",
                        "description": "HTML template for Telegram. Falls back to message_template.",
                    },
                    "eink_template": {
                        "type": "string",
                        "description": "Short plain-text template for eInk displays. Falls back to message_template.",
                    },
                    "tts_template": {
                        "type": "string",
                        "description": "Natural language template for TTS. Falls back to message_template.",
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
                "telegram_template": "",
                "eink_template": "",
                "tts_template": "",
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

        # Determine base message
        message = (
            pipeline_data.get("translation")
            or pipeline_data.get("logic_response", {}).get("user_notification", "")
            or pipeline_data.get("vision_response", "")
        )
        if message_template:
            message = _format_channel_message(
                message_template, message, trigger, pipeline_data
            )

        # Build per-channel messages
        channel_names = [
            "telegram", "eink", "tts", "websocket", "realtime_voice", "homeassistant",
        ]
        channel_messages: dict[str, str] = {}
        for ch in channel_names:
            ch_tmpl = config.get(f"{ch}_template", "")
            if ch_tmpl:
                channel_messages[ch] = _format_channel_message(
                    ch_tmpl, message, trigger, pipeline_data
                )
            # Channels without a specific template get the base message
            # (already formatted by message_template if set).

        # Determine image_url from trigger media (original camera frames)
        image_url: str | None = None
        if trigger.media_paths:
            image_url = trigger.media_paths[0]

        eink_targets = config.get("eink_targets")
        ha_media_player = config.get("ha_media_player")
        rule_config: dict = {}
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
            image_url=image_url,
            rule_config=rule_config if rule_config else None,
            channel_messages=channel_messages if channel_messages else None,
        )

        return StepResult(
            data={
                "notification_dispatched": True,
                "notification_channels": results,
            }
        )
