"""Step plugin registry.

Discovers and registers all :class:`StepHandler` subclasses from
``backend.steps.builtin`` (and optionally ``backend.steps.contrib``).

Usage::

    from backend.steps import StepRegistry

    handler_cls = StepRegistry.get("wait")
    result = await handler_cls().execute(step, execution, data, trigger, svc)
"""

from __future__ import annotations

from backend.core.registry import PluginRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

__all__ = [
    "ServiceContainer",
    "StepHandler",
    "StepMetadata",
    "StepRegistry",
    "StepResult",
    "TriggerContext",
]


class StepRegistry(PluginRegistry[StepHandler, StepMetadata]):
    """Singleton registry of pipeline step handlers."""

    _discovery_packages = ("backend.steps.builtin", "backend.steps.contrib")

    @classmethod
    def _key_from_metadata(cls, meta: StepMetadata) -> str:
        return meta.type_name

    @classmethod
    def get_class(cls, type_name: str) -> type[StepHandler] | None:
        """Return the handler *class* (not instance) for *type_name*."""
        return cls._registry.get(type_name)

    @classmethod
    def type_names(cls) -> list[str]:
        """Return all registered step type names (deprecated alias)."""
        return cls.all_names()
