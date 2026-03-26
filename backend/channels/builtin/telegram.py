"""Telegram notification channel."""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class TelegramChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="telegram",
            display_name="Telegram",
            description="Send notifications to Telegram chats.",
            config_schema={
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "chat_id": {"type": "string"},
                                "alert_levels": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
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
        if not services or not services.telegram_client:
            return False
        try:
            targets = settings.get("notifications.telegram.targets", [])
            for target in targets:
                if alert_level in target.get("alert_levels", []):
                    if image_url:
                        await services.telegram_client.send_photo(
                            target["chat_id"], image_url, caption=message
                        )
                    else:
                        await services.telegram_client.send_message(
                            target["chat_id"], message
                        )
            return True
        except Exception as e:
            logger.error("telegram_dispatch_failed", error=str(e))
            return False
