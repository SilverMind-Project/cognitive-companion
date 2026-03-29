"""Telegram Bot API client using python-telegram-bot.

Provides send helpers for messages, photos (with optional downscaling), voice,
and documents. Images from internal MinIO URLs are always fetched as bytes
before sending since the MinIO endpoint is not reachable from Telegram's
servers.
"""

from __future__ import annotations

from io import BytesIO

import httpx
from PIL import Image

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

_FETCH_TIMEOUT = 30.0  # seconds for downloading images from MinIO


# ---------------------------------------------------------------------------
# Image helpers (module-level, reusable by the channel plugin)
# ---------------------------------------------------------------------------


def scale_image(data: bytes, max_side: int = 1920) -> bytes:
    """Downscale *data* so the longest side is at most *max_side* pixels.

    Returns JPEG bytes. If the image already fits, the original bytes are
    returned unchanged.
    """
    img = Image.open(BytesIO(data))
    w, h = img.size
    if max(w, h) <= max_side:
        return data
    ratio = max_side / max(w, h)
    new_size = (int(w * ratio), int(h * ratio))
    img = img.resize(new_size, Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def fetch_image_bytes(url: str) -> bytes | None:
    """Download an image from *url* and return raw bytes.

    Returns ``None`` on any fetch error so callers can fall back to a
    text-only message.
    """
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception:
        logger.warning("fetch_image_bytes_failed", url=url[:120])
        return None


async def fetch_and_prepare_image(
    url: str,
    max_side: int = 1920,
) -> bytes | None:
    """Fetch an image URL and optionally downscale it.

    Combines :func:`fetch_image_bytes` and :func:`scale_image`. If
    *max_side* is ``0`` or negative, no scaling is applied.
    """
    data = await fetch_image_bytes(url)
    if data is None:
        return None
    if max_side > 0:
        data = scale_image(data, max_side)
    return data


# ---------------------------------------------------------------------------
# TelegramClient
# ---------------------------------------------------------------------------


class TelegramClient:
    """Async wrapper around ``python-telegram-bot``'s ``Bot`` class.

    Instantiates a ``telegram.Bot`` for send-only operations (no polling or
    webhook setup). All methods are safe to call from any ``asyncio`` context.
    """

    def __init__(self) -> None:
        self._bot = None
        self._token: str = ""
        self._configure()

    def _configure(self) -> None:
        token = settings.get("notifications.telegram.bot_token", "")
        if not token:
            logger.warning("telegram_not_configured", reason="missing bot_token")
            return
        self._token = token
        try:
            import telegram

            self._bot = telegram.Bot(token=token)
            logger.info("telegram_client_initialized")
        except Exception:
            logger.exception("telegram_init_failed")

    # -- properties -----------------------------------------------------------

    @property
    def configured(self) -> bool:
        return self._bot is not None

    # -- send helpers ---------------------------------------------------------

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        parse_mode: str | None = "HTML",
    ) -> bool:
        """Send a text message to *chat_id*."""
        if not self._bot:
            return False
        try:
            await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
            )
            logger.info("telegram_message_sent", chat_id=chat_id)
            return True
        except Exception:
            logger.exception("telegram_send_message_failed", chat_id=chat_id)
            return False

    async def send_photo(
        self,
        chat_id: str | int,
        photo: bytes,
        caption: str | None = None,
        parse_mode: str | None = "HTML",
    ) -> bool:
        """Send a photo (bytes) to *chat_id*."""
        if not self._bot:
            return False
        try:
            await self._bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
            )
            logger.info("telegram_photo_sent", chat_id=chat_id)
            return True
        except Exception:
            logger.exception("telegram_send_photo_failed", chat_id=chat_id)
            return False

    async def send_voice(
        self,
        chat_id: str | int,
        voice: bytes,
        caption: str | None = None,
    ) -> bool:
        """Send a voice note (bytes) to *chat_id*."""
        if not self._bot:
            return False
        try:
            await self._bot.send_voice(
                chat_id=chat_id,
                voice=voice,
                caption=caption,
            )
            logger.info("telegram_voice_sent", chat_id=chat_id)
            return True
        except Exception:
            logger.exception("telegram_send_voice_failed", chat_id=chat_id)
            return False

    async def send_document(
        self,
        chat_id: str | int,
        document: bytes,
        caption: str | None = None,
        filename: str = "document",
    ) -> bool:
        """Send a document (bytes) to *chat_id*."""
        if not self._bot:
            return False
        try:
            import telegram

            input_file = telegram.InputFile(document, filename=filename)
            await self._bot.send_document(
                chat_id=chat_id,
                document=input_file,
                caption=caption,
            )
            logger.info("telegram_document_sent", chat_id=chat_id)
            return True
        except Exception:
            logger.exception("telegram_send_document_failed", chat_id=chat_id)
            return False

    async def send_rich_notification(
        self,
        chat_id: str | int,
        text: str,
        image_url: str | None = None,
        max_image_side: int = 1920,
    ) -> bool:
        """Send a notification with optional image.

        The image is always fetched as bytes and optionally downscaled since
        the MinIO endpoint is on a private network. If fetching fails the
        notification falls back to a text-only message.
        """
        if image_url:
            image_bytes = await fetch_and_prepare_image(image_url, max_image_side)
            if image_bytes:
                return await self.send_photo(chat_id, image_bytes, caption=text)
        return await self.send_message(chat_id, text)
