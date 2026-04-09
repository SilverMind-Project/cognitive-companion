"""PWA popup text notification channel.

Broadcasts structured notification payloads to all connected WebSocket
clients.  The frontend renders these as snackbar toasts (info/warning/reminder)
or a persistent dialog (emergency).
"""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class PWAPopupTextChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="pwa_popup_text",
            display_name="PWA Popup Text",
            description="Broadcast text notifications to connected PWA clients via WebSocket.",
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
            payload: dict = {
                "type": alert_level,
                "message": message,
                "room": room_name,
            }
            if image_url:
                payload["image_url"] = image_url
            await services.ws_manager.broadcast(payload)
            return True
        except Exception as e:
            logger.error("pwa_popup_text_dispatch_failed", error=str(e))
            return False
