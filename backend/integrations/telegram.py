"""
Telegram integration – send text, photos, voice, and documents to chats.

Supports rich messages with images/voice stored in local MinIO. Files are
uploaded to Telegram via the Bot API's multipart endpoints.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramClient:
    """Async Telegram Bot API client for sending notifications."""

    def __init__(self) -> None:
        token = settings.get("notifications.telegram.bot_token") or ""
        self.bot_token: str = token
        self._base = f"{TELEGRAM_API}/bot{token}" if token else ""

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self._base)

    # ------------------------------------------------------------------
    # Text messages
    # ------------------------------------------------------------------

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        parse_mode: str = "HTML",
    ) -> dict[str, Any] | None:
        """Send a plain text message."""
        if not self.configured:
            logger.warning("telegram_not_configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self._base}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("telegram_send_message_error", chat_id=chat_id)
            return None

    # ------------------------------------------------------------------
    # Photos
    # ------------------------------------------------------------------

    async def send_photo(
        self,
        chat_id: str | int,
        photo: str | bytes,
        caption: str = "",
    ) -> dict[str, Any] | None:
        """Send a photo.

        ``photo`` can be:
        - A URL string (Telegram will download it)
        - Raw bytes (uploaded as multipart)
        """
        if not self.configured:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if isinstance(photo, bytes):
                    resp = await client.post(
                        f"{self._base}/sendPhoto",
                        data={"chat_id": str(chat_id), "caption": caption},
                        files={"photo": ("photo.jpg", photo, "image/jpeg")},
                    )
                else:
                    resp = await client.post(
                        f"{self._base}/sendPhoto",
                        json={
                            "chat_id": chat_id,
                            "photo": photo,
                            "caption": caption,
                        },
                    )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("telegram_send_photo_error", chat_id=chat_id)
            return None

    # ------------------------------------------------------------------
    # Voice messages
    # ------------------------------------------------------------------

    async def send_voice(
        self,
        chat_id: str | int,
        voice: str | bytes,
        caption: str = "",
    ) -> dict[str, Any] | None:
        """Send a voice message (OGG Opus or URL)."""
        if not self.configured:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if isinstance(voice, bytes):
                    resp = await client.post(
                        f"{self._base}/sendVoice",
                        data={"chat_id": str(chat_id), "caption": caption},
                        files={"voice": ("voice.ogg", voice, "audio/ogg")},
                    )
                else:
                    resp = await client.post(
                        f"{self._base}/sendVoice",
                        json={
                            "chat_id": chat_id,
                            "voice": voice,
                            "caption": caption,
                        },
                    )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("telegram_send_voice_error", chat_id=chat_id)
            return None

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def send_document(
        self,
        chat_id: str | int,
        document: str | bytes,
        filename: str = "file",
        caption: str = "",
    ) -> dict[str, Any] | None:
        """Send an arbitrary file as a document."""
        if not self.configured:
            return None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if isinstance(document, bytes):
                    resp = await client.post(
                        f"{self._base}/sendDocument",
                        data={"chat_id": str(chat_id), "caption": caption},
                        files={"document": (filename, document)},
                    )
                else:
                    resp = await client.post(
                        f"{self._base}/sendDocument",
                        json={
                            "chat_id": chat_id,
                            "document": document,
                            "caption": caption,
                        },
                    )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("telegram_send_document_error", chat_id=chat_id)
            return None

    # ------------------------------------------------------------------
    # Rich message (image + voice from MinIO)
    # ------------------------------------------------------------------

    async def send_rich_notification(
        self,
        chat_id: str | int,
        text: str,
        image_url: str | None = None,
        voice_url: str | None = None,
        minio_client=None,
    ) -> None:
        """Send a rich notification with optional image and voice.

        If ``minio_client`` is provided, URLs are assumed to be MinIO presigned
        URLs. The file bytes are fetched and uploaded directly to Telegram.
        """
        # Send text
        await self.send_message(chat_id, text)

        # Send image if available
        if image_url:
            if minio_client:
                image_bytes = await _fetch_url_bytes(image_url)
                if image_bytes:
                    await self.send_photo(chat_id, image_bytes, caption="Alert image")
            else:
                await self.send_photo(chat_id, image_url, caption="Alert image")

        # Send voice if available
        if voice_url:
            if minio_client:
                voice_bytes = await _fetch_url_bytes(voice_url)
                if voice_bytes:
                    await self.send_voice(chat_id, voice_bytes, caption="Voice alert")
            else:
                await self.send_voice(chat_id, voice_url, caption="Voice alert")


async def _fetch_url_bytes(url: str) -> bytes | None:
    """Download file bytes from a URL (e.g. MinIO presigned URL)."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception:
        logger.exception("fetch_url_bytes_error", url=url[:80])
        return None
