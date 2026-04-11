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
    minio_client: Any = None
    ha_client: Any = None


class NotificationDispatcher:
    """Dispatches notifications to registered channels via the ChannelRegistry."""

    def __init__(
        self,
        telegram_client=None,
        ws_manager=None,
        tts_client=None,
        image_renderer=None,
        minio_client=None,
        ha_client=None,
    ) -> None:
        self._dispatch_services = DispatchServices(
            ws_manager=ws_manager,
            telegram_client=telegram_client,
            tts_client=tts_client,
            image_renderer=image_renderer,
            minio_client=minio_client,
            ha_client=ha_client,
        )

    async def dispatch(
        self,
        alert_level: str,
        message: str,
        room_name: str,
        image_url: str | None = None,
        rule_config: dict | None = None,
        channel_messages: dict[str, str] | None = None,
    ) -> dict[str, bool]:
        """
        Route notification to configured channels based on alert_level.

        *channel_messages* is an optional dict mapping channel names to
        channel-specific formatted messages. Channels not in the dict
        receive the default *message*.

        Returns dict of channel -> success.
        """
        # Per-step channel overrides take precedence over config-file defaults
        override_channels = (rule_config or {}).get("channels") if rule_config else None

        if override_channels:
            channels = override_channels
        else:
            notif_cfg = settings.get("notifications.notification_defaults", {})
            level_cfg = notif_cfg.get(alert_level, {})
            channels = level_cfg.get("channels", ["websocket"])

        results: dict[str, bool] = {}

        for channel_name in channels:
            channel = ChannelRegistry.get(channel_name)
            if not channel:
                logger.warning("unknown_channel", channel=channel_name)
                continue

            channel_config = rule_config or {}

            # Resolve per-channel message, falling back to default
            ch_message = (channel_messages or {}).get(channel_name, message)

            success = await channel.send(
                message=ch_message,
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
