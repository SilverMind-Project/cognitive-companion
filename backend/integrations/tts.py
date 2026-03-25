"""
Text-to-Speech integration using an OpenAI-compatible TTS API.

Used for generating voice alerts played on smart speakers via Home Assistant
and for TTS audio sent through Telegram.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class TTSClient:
    """Async TTS client compatible with OpenAI /v1/audio/speech endpoint."""

    def __init__(self) -> None:
        base_url = settings.get("tts.url") or ""
        if base_url and "/v1" not in base_url:
            base_url = base_url.rstrip("/") + "/v1"
        self.base_url = base_url.rstrip("/")
        self.default_voice = settings.get("tts.default_voice", "en-IN-NeerjaExpressiveNeural")
        self.default_speed = settings.get("tts.default_speed", 0.85)

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    async def generate_audio(
        self,
        text: str,
        voice: str | None = None,
        speed: float | None = None,
        response_format: str = "mp3",
    ) -> bytes | None:
        """Generate audio from text and return raw bytes.

        Returns None on failure.
        """
        if not self.configured:
            logger.warning("tts_not_configured")
            return None

        voice = voice or self.default_voice
        speed = speed if speed is not None else self.default_speed

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/audio/speech",
                    json={
                        "model": "tts-1",
                        "voice": voice,
                        "input": text,
                        "speed": speed,
                        "response_format": response_format,
                    },
                    headers={"Authorization": "Bearer EMPTY"},
                )
                resp.raise_for_status()
                return resp.content
        except Exception:
            logger.exception("tts_generate_error", text=text[:60])
            return None

    async def generate_and_upload(
        self,
        text: str,
        minio_client,
        voice: str | None = None,
        speed: float | None = None,
    ) -> str | None:
        """Generate TTS audio, upload to MinIO, and return the presigned URL."""
        audio_bytes = await self.generate_audio(text, voice=voice, speed=speed)
        if not audio_bytes:
            return None

        object_name = f"tts/{uuid.uuid4().hex[:12]}.mp3"
        try:
            url = minio_client.upload_bytes(
                data=audio_bytes,
                object_name=object_name,
                content_type="audio/mpeg",
            )
            logger.info("tts_uploaded", object_name=object_name)
            return url
        except Exception:
            logger.exception("tts_upload_error")
            return None
