"""PWA announcement notification channel.

Delivers audio announcements directly to connected PWA clients via WebSocket.
Supports two modes:

- **stream**: Real-time TTS synthesis streamed as PCM int16 chunks through
  the WebSocket.  The frontend plays chunks as they arrive using the Web
  Audio API for gapless playback.
- **file**: Sends a presigned URL pointing to a pre-rendered audio file.
  The frontend plays it via the HTML5 Audio API.

WebSocket protocol (stream mode)::

    Server -> Client  JSON  {type: "announcement", subtype: "stream_start", sample_rate: 24000}
    Server -> Client  bytes (PCM int16 LE chunks)
    Server -> Client  JSON  {type: "announcement", subtype: "stream_end"}

WebSocket protocol (file mode)::

    Server -> Client  JSON  {type: "announcement", subtype: "audio_url", url: "..."}
"""

from __future__ import annotations

from backend.channels import ChannelRegistry
from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)


@ChannelRegistry.register
class AnnouncementChannel(NotificationChannel):

    @classmethod
    def metadata(cls) -> ChannelMetadata:
        return ChannelMetadata(
            channel_name="announcement",
            display_name="PWA Announcement",
            description=(
                "Stream TTS audio or play audio files directly on connected "
                "PWA clients via WebSocket."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["stream", "file"],
                        "description": (
                            "stream = real-time TTS streaming, "
                            "file = play a pre-rendered audio URL"
                        ),
                    },
                    "audio_url": {
                        "type": "string",
                        "description": "URL of audio file to play (mode=file only)",
                    },
                    "tts_language": {
                        "type": "string",
                        "description": "Language code for TTS (e.g. 'ta', 'en')",
                    },
                    "tts_style": {
                        "type": "string",
                        "description": "Svara style tag (e.g. 'clear', 'formal')",
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
        config = config or {}
        ws_manager = getattr(services, "ws_manager", None)

        if not ws_manager or not ws_manager.has_connections:
            logger.warning("announcement_no_ws_clients")
            return False

        mode = config.get("mode", "stream")

        if mode == "file":
            return await self._send_file(ws_manager, message, config)

        return await self._send_stream(ws_manager, services, message, config)

    async def _send_stream(self, ws_manager, services, message: str, config: dict) -> bool:
        """Stream TTS audio to all connected WebSocket clients."""
        tts_client = getattr(services, "tts_client", None)
        if not tts_client or not tts_client.configured:
            logger.warning("announcement_tts_not_configured")
            return False

        language = config.get("tts_language")
        style = config.get("tts_style")

        audio_stream = await tts_client.stream_audio(
            message, language=language, style=style,
        )
        if not audio_stream:
            logger.warning("announcement_stream_failed", message=message[:60])
            return False

        # Signal stream start
        await ws_manager.broadcast({
            "type": "announcement",
            "subtype": "stream_start",
            "sample_rate": audio_stream.sample_rate,
            "message": message,
        })

        # Stream PCM chunks as binary frames
        chunk_count = 0
        async for chunk in audio_stream.chunks:
            await ws_manager.broadcast_bytes(chunk)
            chunk_count += 1

        # Signal stream end
        await ws_manager.broadcast({
            "type": "announcement",
            "subtype": "stream_end",
        })

        logger.info(
            "announcement_streamed",
            message=message[:60],
            chunks=chunk_count,
        )
        return True

    async def _send_file(self, ws_manager, message: str, config: dict) -> bool:
        """Send an audio file URL for playback."""
        audio_url = config.get("audio_url")
        if not audio_url:
            logger.warning("announcement_no_audio_url")
            return False

        await ws_manager.broadcast({
            "type": "announcement",
            "subtype": "audio_url",
            "url": audio_url,
            "message": message,
        })

        logger.info("announcement_file_sent", url=audio_url)
        return True
