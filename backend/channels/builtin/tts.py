"""Text-to-speech notification channel.

Generates audio via the TTS service, uploads it to MinIO to obtain a
presigned URL, and plays it on the configured Home Assistant media player.
The ``ha_media_player`` key in the notification step's ``config_json``
selects the target entity (defaults to ``media_player.living_room_speaker``).
"""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_MEDIA_PLAYER = "media_player.living_room_speaker"


@ChannelRegistry.register
class TTSChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="tts",
            display_name="Text-to-Speech",
            description="Speak notifications via the TTS service through a Home Assistant media player.",
            config_schema={
                "type": "object",
                "properties": {
                    "ha_media_player": {
                        "type": "string",
                        "description": "HA media_player entity to play audio on",
                    }
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
        config = config or {}
        tts_client = getattr(services, "tts_client", None)
        minio_client = getattr(services, "minio_client", None)
        ha_client = getattr(services, "ha_client", None)

        if not tts_client or not tts_client.configured:
            logger.warning("tts_channel_not_configured")
            return False

        entity_id: str = config.get("ha_media_player") or _DEFAULT_MEDIA_PLAYER

        if minio_client and ha_client and ha_client.configured:
            url = await tts_client.generate_and_upload(message, minio_client)
            if not url:
                return False
            await ha_client.play_audio(url, entity_id)
            logger.info("tts_played_via_ha", entity_id=entity_id)
            return True

        # Fallback: generate audio locally (no HA playback)
        audio = await tts_client.generate_audio(message)
        if audio:
            logger.info("tts_generated_local_only", bytes=len(audio))
        return audio is not None
