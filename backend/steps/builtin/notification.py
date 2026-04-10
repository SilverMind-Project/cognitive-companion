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


# Channels that support per-channel template overrides.
# pwa_tts_announcement intentionally reuses the ha_speaker_tts_template
# since both channels feed the same TTS engine.
_CHANNEL_TEMPLATE_FIELDS: dict[str, str] = {
    "telegram": "telegram_template",
    "eink": "eink_template",
    "ha_speaker_tts": "ha_speaker_tts_template",
    "pwa_tts_announcement": "ha_speaker_tts_template",  # reuses speaker template
    "pwa_popup_text": "pwa_popup_text_template",
    "pwa_realtime_ai": "pwa_realtime_ai_template",
    "webhook": "webhook_template",
}


@StepRegistry.register
class NotificationHandler(StepHandler):

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="notification",
            display_name="Notification",
            category="action",
            icon="mdi-bell",
            description=(
                "Dispatch notifications to configured channels "
                "(PWA Popup Text, Telegram, eInk, HA Speaker TTS, etc.)."
            ),
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
                    "ha_speaker_tts_template": {
                        "type": "string",
                        "description": (
                            "Natural language template for smart speaker TTS and PWA TTS "
                            "announcements. Falls back to message_template."
                        ),
                    },
                    "pwa_popup_text_template": {
                        "type": "string",
                        "description": "Notification text shown in the companion UI overlay. Falls back to message_template.",
                    },
                    "pwa_realtime_ai_template": {
                        "type": "string",
                        "description": "Conversational voice prompt for Gemini Live delivery. Falls back to message_template.",
                    },
                    "webhook_url": {
                        "type": "string",
                        "description": "URL for webhook channel routing",
                    },
                    "webhook_template": {
                        "type": "string",
                        "description": (
                            "JSON payload template for webhook. "
                            "Use {message}, {room}, etc. Falls back to basic JSON."
                        ),
                    },
                    "eink_targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sensor IDs of eink displays (empty = all)",
                    },
                    "eink_template_id": {
                        "type": "integer",
                        "description": (
                            "ID of the image template to render onto. "
                            "Leave empty to use the default alert template."
                        ),
                    },
                    "eink_expiry_minutes": {
                        "type": "integer",
                        "default": 30,
                        "description": (
                            "Number of minutes before the rendered image expires "
                            "and the display reverts to the default template."
                        ),
                    },
                    "ha_media_player": {
                        "type": "string",
                        "description": "HA media_player entity ID for TTS playback",
                    },
                    "trigger_cooloff": {
                        "type": "boolean",
                        "default": True,
                        "description": (
                            "If true, flags this rule for a rate-limit "
                            "cool-off period after completion."
                        ),
                    },
                    "telegram_image_source": {
                        "type": "string",
                        "enum": ["trigger", "none", "additional", "both"],
                        "default": "trigger",
                        "description": (
                            "Image to attach to the Telegram notification. "
                            "'trigger' = frame that triggered the pipeline, "
                            "'additional' = extra cameras only, "
                            "'both' = trigger frame + additional cameras, "
                            "'none' = text only."
                        ),
                    },
                    "telegram_additional_sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra camera sensor IDs to pull images from for Telegram.",
                    },
                    "telegram_additional_room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Pull images from all cameras in these rooms for Telegram.",
                    },
                    "telegram_images_per_sensor": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "description": (
                            "Maximum images per sensor when "
                            "telegram_sort_by_sensor_then_time is enabled."
                        ),
                    },
                    "telegram_sort_by_sensor_then_time": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "When true, images are grouped by sensor then sorted "
                            "oldest-first within each group."
                        ),
                    },
                    "telegram_image_time_filter": {
                        "type": "object",
                        "properties": {
                            "since_minutes": {"type": "number"},
                            "time_start": {"type": "string"},
                            "time_end": {"type": "string"},
                        },
                        "description": "Time filter for additional camera images sent via Telegram.",
                    },
                },
            },
            default_config={
                "alert_level": "warning",
                "channels": [],
                "message_template": "",
                "telegram_template": "",
                "eink_template": "",
                "ha_speaker_tts_template": "",
                "pwa_popup_text_template": "",
                "pwa_realtime_ai_template": "",
                "webhook_template": "",
                "webhook_url": "",
                "eink_targets": [],
                "eink_template_id": None,
                "eink_expiry_minutes": 30,
                "ha_media_player": "",
                "trigger_cooloff": True,
                "telegram_image_source": "trigger",
                "telegram_additional_sensor_ids": [],
                "telegram_additional_room_names": [],
                "telegram_images_per_sensor": 1,
                "telegram_sort_by_sensor_then_time": False,
                "telegram_image_time_filter": {},
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

        # Build per-channel messages using the template mapping
        channel_messages: dict[str, str] = {}
        for ch_name, tmpl_field in _CHANNEL_TEMPLATE_FIELDS.items():
            ch_tmpl = config.get(tmpl_field, "")
            if ch_tmpl:
                channel_messages[ch_name] = _format_channel_message(
                    ch_tmpl, message, trigger, pipeline_data
                )
            # Channels without a specific template get the base message
            # (already formatted by message_template if set).

        # Assemble image for Telegram using the configured image source
        telegram_image_source: str = config.get("telegram_image_source", "trigger")
        media_paths: list[str] = []

        if telegram_image_source != "none":
            if telegram_image_source in ("trigger", "both"):
                media_paths.extend(trigger.media_paths)

            if telegram_image_source in ("additional", "both") and services.event_aggregator:
                additional_sensors: list[str] = config.get("telegram_additional_sensor_ids") or []
                additional_rooms: list[str] = config.get("telegram_additional_room_names") or []
                time_filter: dict = config.get("telegram_image_time_filter") or {}
                sort_by_sensor: bool = bool(config.get("telegram_sort_by_sensor_then_time", False))
                images_per_sensor: int = int(config.get("telegram_images_per_sensor", 1))

                if sort_by_sensor and additional_sensors:
                    extra = await services.event_aggregator.query_media_by_sensor(
                        sensor_ids_ordered=additional_sensors,
                        images_per_sensor=images_per_sensor,
                        max_images=images_per_sensor * len(additional_sensors),
                        since_minutes=time_filter.get("since_minutes"),
                        time_start=time_filter.get("time_start"),
                        time_end=time_filter.get("time_end"),
                    )
                else:
                    extra = await services.event_aggregator.query_recent_media(
                        sensor_ids=additional_sensors if additional_sensors else None,
                        room_names=additional_rooms if additional_rooms else None,
                        limit=5,
                        since_minutes=time_filter.get("since_minutes"),
                        time_start=time_filter.get("time_start"),
                        time_end=time_filter.get("time_end"),
                    )
                media_paths.extend(extra)

        image_url: str | None = media_paths[0] if media_paths else None

        eink_targets = config.get("eink_targets")
        eink_template_id = config.get("eink_template_id")
        eink_expiry_minutes = config.get("eink_expiry_minutes")
        ha_media_player = config.get("ha_media_player")
        webhook_url = config.get("webhook_url")
        rule_config: dict = {}
        if channels:
            rule_config["channels"] = channels
        if eink_targets:
            rule_config["eink_targets"] = eink_targets
        if eink_template_id is not None:
            rule_config["eink_template_id"] = eink_template_id
        if eink_expiry_minutes is not None:
            rule_config["eink_expiry_minutes"] = eink_expiry_minutes
        if ha_media_player:
            rule_config["ha_media_player"] = ha_media_player
        if webhook_url:
            rule_config["webhook_url"] = webhook_url

        results = await services.notification_dispatcher.dispatch(
            alert_level=alert_level,
            message=message,
            room_name=trigger.room_name or "Unknown",
            image_url=image_url,
            rule_config=rule_config if rule_config else None,
            channel_messages=channel_messages if channel_messages else None,
        )

        result_data = {
            "notification_dispatched": True,
            "notification_channels": results,
        }

        if config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True

        return StepResult(data=result_data)
