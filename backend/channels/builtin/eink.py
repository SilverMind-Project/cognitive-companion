"""E-Ink display notification channel."""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)


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
            eink_targets = (config or {}).get("eink_targets")
            await services.image_renderer(
                text=message, template="alert", sensor_ids=eink_targets
            )
            return True
        except Exception as e:
            logger.error("eink_dispatch_failed", error=str(e))
            return False
