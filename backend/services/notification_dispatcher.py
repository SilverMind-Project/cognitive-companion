"""
Routes notifications to configured channels using the ChannelRegistry plugin system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.channels import ChannelRegistry
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DispatchServices:
    """Bag of services passed to channel plugins during dispatch."""

    ws_manager: Any = None
    telegram_client: Any = None
    tts_client: Any = None
    image_renderer: Any = None


class NotificationDispatcher:
    """Dispatches notifications to registered channels via the ChannelRegistry."""

    def __init__(
        self,
        telegram_client=None,
        ws_manager=None,
        tts_client=None,
        image_renderer=None,
    ) -> None:
        self._dispatch_services = DispatchServices(
            ws_manager=ws_manager,
            telegram_client=telegram_client,
            tts_client=tts_client,
            image_renderer=image_renderer,
        )

    async def dispatch(
        self,
        alert_level: str,
        message: str,
        room_name: str,
        image_url: str | None = None,
        rule_config: dict | None = None,
    ) -> dict[str, bool]:
        """
        Route notification to configured channels based on alert_level.
        Returns dict of channel -> success.
        """
        notif_cfg = settings.get("notifications.notification_defaults", {})
        level_cfg = notif_cfg.get(alert_level, {})
        channels = level_cfg.get("channels", ["websocket"])

        results: dict[str, bool] = {}

        for channel_name in channels:
            channel = ChannelRegistry.get(channel_name)
            if not channel:
                logger.warning("unknown_channel", channel=channel_name)
                continue

            # Build per-channel config from rule_config
            channel_config = {}
            if rule_config:
                channel_config = rule_config

            success = await channel.send(
                message=message,
                alert_level=alert_level,
                room_name=room_name,
                image_url=image_url,
                config=channel_config,
                services=self._dispatch_services,
            )
            results[channel_name] = success

        logger.info(
            "notification_dispatched",
            alert_level=alert_level,
            room=room_name,
            channels=results,
        )
        return results
