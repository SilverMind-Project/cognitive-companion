"""E-Ink display notification channel."""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_EXPIRY_MINUTES = 30


@ChannelRegistry.register
class EInkChannel(NotificationChannel):
    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="eink",
            display_name="E-Ink Display",
            description="Render notifications on connected e-ink displays.",
            config_schema={
                "type": "object",
                "properties": {
                    "eink_targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sensor IDs of eink devices (empty = all)",
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
                        "default": _DEFAULT_EXPIRY_MINUTES,
                        "description": (
                            "Number of minutes before the rendered image expires "
                            "and the display reverts to the default template."
                        ),
                    },
                },
            },
        )

    async def send(
        self,
        message: str,
        alert_level: str,
        room_name: str,
        image_url: str | None = None,
        config: dict | None = None,
        services=None,
    ) -> bool:
        if not services or not services.image_renderer:
            return False
        try:
            config = config or {}
            eink_targets = config.get("eink_targets")
            template_id = config.get("eink_template_id")
            expiry_minutes = config.get("eink_expiry_minutes", _DEFAULT_EXPIRY_MINUTES)

            await services.image_renderer(
                text=message,
                template="alert",
                template_id=template_id,
                sensor_ids=eink_targets,
                expires_in_minutes=expiry_minutes,
            )
            return True
        except Exception as e:
            logger.error("eink_dispatch_failed", error=str(e))
            return False
