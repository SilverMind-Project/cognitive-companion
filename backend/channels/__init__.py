"""Notification channel registry.

Discovers and registers all :class:`NotificationChannel` subclasses.

Usage::

    from backend.channels import ChannelRegistry

    channel = ChannelRegistry.get("telegram")
    success = await channel.send(message, alert_level, room_name)
"""

from __future__ import annotations

from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.registry import PluginRegistry

__all__ = [
    "ChannelMetadata",
    "ChannelRegistry",
    "NotificationChannel",
]


class ChannelRegistry(PluginRegistry[NotificationChannel, ChannelMetadata]):
    """Singleton registry of notification channels."""

    _discovery_packages = ("backend.channels.builtin",)

    @classmethod
    def _key_from_metadata(cls, meta: ChannelMetadata) -> str:
        return meta.channel_name

    @classmethod
    def channel_names(cls) -> list[str]:
        """Return all registered channel names (deprecated alias)."""
        return cls.all_names()
