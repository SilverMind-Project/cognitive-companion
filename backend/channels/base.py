"""Notification channel plugin base class.

Each channel (Telegram, WebSocket, eInk, TTS, etc.) implements
:class:`NotificationChannel` and is auto-discovered by the
:class:`ChannelRegistry`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ChannelMetadata:
    """Declarative metadata for a notification channel."""

    channel_name: str  # "telegram"
    display_name: str  # "Telegram"
    description: str
    config_schema: dict  # JSONSchema for per-channel config


class NotificationChannel(ABC):
    """Base class for notification channel plugins."""

    @classmethod
    @abstractmethod
    def metadata(cls) -> ChannelMetadata:
        """Return channel metadata."""
        ...

    @abstractmethod
    async def send(
        self,
        message: str,
        alert_level: str,
        room_name: str,
        image_url: str | None = None,
        config: dict | None = None,
        services: Any = None,
    ) -> bool:
        """Send a notification. Return True on success."""
        ...
