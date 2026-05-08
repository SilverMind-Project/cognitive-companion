"""Context filter registry.

Discovers and registers all :class:`ContextFilter` subclasses.

Usage::

    from backend.filters import FilterRegistry

    f = FilterRegistry.get("room")
    passed = f.evaluate(config, sensor, now, db)
"""

from __future__ import annotations

from backend.core.registry import PluginRegistry
from backend.filters.base import ContextFilter, FilterMetadata

__all__ = [
    "ContextFilter",
    "FilterMetadata",
    "FilterRegistry",
]


class FilterRegistry(PluginRegistry[ContextFilter, FilterMetadata]):
    """Singleton registry of context filter types."""

    _discovery_packages = ("backend.filters.builtin",)

    @classmethod
    def _key_from_metadata(cls, meta: FilterMetadata) -> str:
        return meta.filter_type

    @classmethod
    def filter_types(cls) -> list[str]:
        """Return all registered filter type names (deprecated alias)."""
        return cls.all_names()
