"""Text-to-speech notification channel."""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class TTSChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="tts",
            display_name="Text-to-Speech",
            description="Speak notifications via the TTS service.",
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
        # TTS is handled by the realtime session; here we just acknowledge intent
        return True
