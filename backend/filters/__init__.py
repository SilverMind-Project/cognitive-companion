"""Context filter registry.

Discovers and registers all :class:`ContextFilter` subclasses.

Usage::

    from backend.filters import FilterRegistry

    f = FilterRegistry.get("room")
    passed = f.evaluate(config, sensor, now, db)
"""

from __future__ import annotations

import importlib
import pkgutil

from backend.core.logging import get_logger
from backend.filters.base import ContextFilter, FilterMetadata

logger = get_logger(__name__)

__all__ = [
    "ContextFilter",
    "FilterMetadata",
    "FilterRegistry",
]


class FilterRegistry:
    """Singleton registry of context filter types."""

    _filters: dict[str, type[ContextFilter]] = {}
    _instances: dict[str, ContextFilter] = {}

    @classmethod
    def register(cls, filter_class: type[ContextFilter]) -> type[ContextFilter]:
        """Register a filter class. Can be used as a decorator."""
        meta = filter_class.metadata()
        cls._filters[meta.filter_type] = filter_class
        cls._instances[meta.filter_type] = filter_class()
        logger.debug("filter_registered", filter_type=meta.filter_type)
        return filter_class

    @classmethod
    def get(cls, filter_type: str) -> ContextFilter | None:
        """Return the singleton filter instance."""
        return cls._instances.get(filter_type)

    @classmethod
    def all_metadata(cls) -> list[FilterMetadata]:
        """Return metadata for all registered filters."""
        return [f.metadata() for f in cls._filters.values()]

    @classmethod
    def filter_types(cls) -> list[str]:
        """Return all registered filter type names."""
        return list(cls._filters.keys())

    @classmethod
    def discover(cls) -> None:
        """Auto-discover and register filters from builtin/."""
        for package_name in ("backend.filters.builtin",):
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
                        "filter_discovery_failed",
                        module=module_name,
                        error=str(e),
                    )
