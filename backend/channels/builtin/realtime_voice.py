"""PWA realtime AI notification channel.

Queues an interactive voice prompt on the WebSocket backend task queue for
delivery via the active Gemini Live session. Unlike HA Speaker TTS (a one-way
announcement), this channel initiates a two-way conversation: the AI speaks
the message and waits for a spoken response from the user.

If no Gemini Live session is currently active the prompt is silently dropped.
Pair this channel with ``pwa_popup_text`` or ``telegram`` to ensure delivery
when the companion UI is not open.
"""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class PWARealtimeAIChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="pwa_realtime_ai",
            display_name="PWA Realtime AI",
            description=(
                "Queue an interactive voice prompt via the active Gemini Live "
                "session. The AI speaks the message and listens for a response."
            ),
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

        async def _log_response(response_text: str) -> None:
            logger.info(
                "pwa_realtime_ai_response",
                room=room_name,
                response=response_text[:120],
            )

        try:
            await services.ws_manager.send_backend_task(
                prompt=message,
                callback=_log_response,
            )
            return True
        except Exception as e:
            logger.error("pwa_realtime_ai_dispatch_failed", error=str(e))
            return False
