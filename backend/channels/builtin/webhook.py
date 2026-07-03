"""Webhook notification channel.

Dispatches notifications via an outbound HTTP POST call. Supports
payload templates and fallback configurations from settings.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class WebhookChannel(NotificationChannel):
    """Notification channel for outbound webhooks."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient()
        self._default_timeout = settings.as_float("notifications.webhook.timeout_seconds")

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="webhook",
            display_name="Outbound Webhook",
            description="Send an HTTP POST webhook.",
            config_schema={},
        )

    async def send(
        self,
        message: str,
        alert_level: str,
        room_name: str,
        image_url: str | None = None,
        image_urls: list[str] | None = None,
        config: dict | None = None,
        services: Any = None,
    ) -> bool:
        """Send a notification via webhook."""
        config = config or {}

        url = config.get("webhook_url")
        if not url:
            url = settings.as_str("notifications.webhook.url")

        if not url:
            logger.warning("webhook_channel_skipped", reason="No webhook URL available")
            return False

        try:
            # message holds the templated `webhook_template` JSON
            # if one was defined, or fallback textual message.
            # We try parsing the payload to send JSON natively.
            payload = json.loads(message)
        except json.JSONDecodeError, TypeError:
            payload = {
                "message": message,
                "alert_level": alert_level,
                "room": room_name,
                "image_url": image_url,
            }

        headers = settings.as_dict("notifications.webhook.headers")
        timeout = float(settings.as_float("notifications.webhook.timeout_seconds"))

        try:
            response = await self._client.post(
                str(url),
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            logger.info("webhook_notification_sent", url=url, status_code=response.status_code)
            return True
        except Exception as exc:
            logger.warning("webhook_notification_failed", error=str(exc), url=url)
            return False
