"""Telegram notification channel.

Images are always fetched as bytes from their URL (MinIO is on a private
network) and optionally downscaled before sending. The ``max_image_side``
setting in ``notifications.yaml`` controls the maximum longest-side length
in pixels (default 1920; set to 0 to disable scaling).
"""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.telegram import fetch_and_prepare_image

logger = get_logger(__name__)


@ChannelRegistry.register
class TelegramChannel(NotificationChannel):
    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="telegram",
            display_name="Telegram",
            description="Send notifications to Telegram chats via the Bot API.",
            config_schema={
                "type": "object",
                "properties": {
                    "telegram_targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override target chat_ids (empty = use notifications.yaml)",
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
        image_urls: list[str] | None = None,
        config: dict | None = None,
        services=None,
    ) -> bool:
        if not services or not services.telegram_client:
            return False
        if not services.telegram_client.configured:
            return False

        targets = settings.get("notifications.telegram.targets", [])
        if not targets:
            logger.warning("telegram_no_targets")
            return False

        max_side = settings.get("notifications.telegram.max_image_side", 1920)
        any_sent = False

        # Resolve the list of URLs to send (image_urls supersedes image_url)
        urls: list[str] = image_urls if image_urls else ([image_url] if image_url else [])

        # Pre-fetch and scale all images once, shared across targets
        all_image_bytes: list[bytes] = []
        for url in urls:
            data = await fetch_and_prepare_image(url, max_side)
            if data:
                all_image_bytes.append(data)

        for target in targets:
            target_levels = target.get("alert_levels", [])
            if alert_level not in target_levels:
                continue

            chat_id = target.get("chat_id")
            if not chat_id:
                continue

            if len(all_image_bytes) > 1:
                ok = await services.telegram_client.send_media_group(
                    chat_id, all_image_bytes, caption=message
                )
            elif len(all_image_bytes) == 1:
                ok = await services.telegram_client.send_photo(
                    chat_id, all_image_bytes[0], caption=message
                )
            else:
                ok = await services.telegram_client.send_message(chat_id, message)

            if ok:
                any_sent = True

        return any_sent
