"""WebSocket notification channel."""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class WebSocketChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="websocket",
            display_name="WebSocket",
            description="Broadcast notifications to connected WebSocket clients.",
            config_schema={"type": "object", "properties": {}},
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
        if not services or not services.ws_manager:
            return False
        try:
            await services.ws_manager.broadcast({
                "type": alert_level,
                "message": message,
                "room": room_name,
            })
            return True
        except Exception as e:
            logger.error("ws_dispatch_failed", error=str(e))
            return False
