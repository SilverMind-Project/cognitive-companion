"""Notification channel registry.

Discovers and registers all :class:`NotificationChannel` subclasses.

Usage::

    from backend.channels import ChannelRegistry

    channel = ChannelRegistry.get("telegram")
    success = await channel.send(message, alert_level, room_name)
"""

from __future__ import annotations

import importlib
import pkgutil

from backend.channels.base import ChannelMetadata, NotificationChannel
from backend.core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "ChannelMetadata",
    "ChannelRegistry",
    "NotificationChannel",
]


class ChannelRegistry:
    """Singleton registry of notification channels."""

    _channels: dict[str, type[NotificationChannel]] = {}
    _instances: dict[str, NotificationChannel] = {}

    @classmethod
    def register(cls, channel_class: type[NotificationChannel]) -> type[NotificationChannel]:
        """Register a channel class. Can be used as a decorator."""
        meta = channel_class.metadata()
        cls._channels[meta.channel_name] = channel_class
        cls._instances[meta.channel_name] = channel_class()
        logger.debug("channel_registered", channel=meta.channel_name)
        return channel_class

    @classmethod
    def get(cls, channel_name: str) -> NotificationChannel | None:
        """Return the singleton channel instance."""
        return cls._instances.get(channel_name)

    @classmethod
    def all_metadata(cls) -> list[ChannelMetadata]:
        """Return metadata for all registered channels."""
        return [c.metadata() for c in cls._channels.values()]

    @classmethod
    def channel_names(cls) -> list[str]:
        """Return all registered channel names."""
        return list(cls._channels.keys())

    @classmethod
    def discover(cls) -> None:
        """Auto-discover and register channels from builtin/."""
        for package_name in ("backend.channels.builtin",):
            try:
                package = importlib.import_module(package_name)
            except ImportError:
                continue
            for _importer, module_name, _ispkg in pkgutil.iter_modules(
                package.__path__, package.__name__ + "."
            ):
                try:
                    importlib.import_module(module_name)
                except Exception as e:
                    logger.warning(
                        "channel_discovery_failed",
                        module=module_name,
                        error=str(e),
                    )
