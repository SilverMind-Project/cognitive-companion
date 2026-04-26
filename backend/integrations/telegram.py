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
    img = img.resize(new_size, Image.Resampling.LANCZOS)  # type: ignore[assignment]
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
        from typing import Any

        self._bot: Any = None
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

    async def send_media_group(
        self,
        chat_id: str | int,
        photos: list[bytes],
        caption: str | None = None,
        parse_mode: str | None = "HTML",
    ) -> bool:
        """Send multiple photos as a Telegram media group (album).

        The caption is attached to the first photo only, which is how Telegram
        displays album captions. Falls back to a single send_photo call when
        only one photo is supplied.
        """
        if not self._bot:
            return False
        if not photos:
            return False
        if len(photos) == 1:
            return await self.send_photo(chat_id, photos[0], caption=caption)
        try:
            import telegram

            media = [
                telegram.InputMediaPhoto(
                    media=photo,
                    caption=caption if i == 0 else None,
                    parse_mode=parse_mode if i == 0 else None,
                )
                for i, photo in enumerate(photos)
            ]
            await self._bot.send_media_group(chat_id=chat_id, media=media)
            logger.info("telegram_media_group_sent", chat_id=chat_id, count=len(photos))
            return True
        except Exception:
            logger.exception("telegram_send_media_group_failed", chat_id=chat_id)
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

    async def setup_polling(self, drop_pending_updates: bool = False) -> bool:
        """Prepare the bot for getUpdates polling.

        In python-telegram-bot v21 the Bot object must be initialised (which
        sets up the underlying httpx connection pool) before API calls are
        made reliably.  This method also removes any registered webhook, since
        Telegram silently withholds updates from ``getUpdates`` while a
        webhook is active.

        Call once at startup before the polling scheduler job is added.
        Set *drop_pending_updates* to ``True`` to discard messages that
        accumulated while a webhook was registered.
        """
        if not self._bot:
            return False
        try:
            await self._bot.initialize()
            me = await self._bot.get_me()
            logger.info("telegram_bot_initialized", username=me.username)
        except Exception:
            logger.exception("telegram_bot_initialize_failed")
            return False
        try:
            await self._bot.delete_webhook(drop_pending_updates=drop_pending_updates)
            logger.info("telegram_polling_ready")
            return True
        except Exception:
            logger.exception("telegram_delete_webhook_failed")
            return False

    async def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """Long-poll for incoming Telegram updates.

        Calls the Bot API ``getUpdates`` endpoint directly via httpx,
        bypassing the python-telegram-bot wrapper to avoid any library-level
        filtering or serialisation quirks.

        Pass *offset* as ``last_update_id + 1`` to acknowledge processed
        updates.  Use ``timeout=0`` for short-polling.

        Returns a list of raw update dicts or an empty list on any error.
        """
        if not self._token:
            logger.warning("get_updates_skipped", reason="no token")
            return []
        params: dict = {"limit": limit, "timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        try:
            async with httpx.AsyncClient(timeout=timeout + 10.0) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{self._token}/getUpdates",
                    params=params,
                )
            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "telegram_get_updates_api_error",
                    description=data.get("description"),
                    error_code=data.get("error_code"),
                )
                return []
            return data.get("result", [])
        except Exception:
            logger.exception("telegram_get_updates_failed")
            return []

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
