"""Step plugin registry.

Discovers and registers all :class:`StepHandler` subclasses from
``backend.steps.builtin`` (and optionally ``backend.steps.contrib``).

Usage::

    from backend.steps import StepRegistry

    handler_cls = StepRegistry.get("wait")
    result = await handler_cls().execute(step, execution, data, trigger, svc)
"""

from __future__ import annotations

import importlib
import pkgutil

from backend.core.logging import get_logger
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

__all__ = [
    "ServiceContainer",
    "StepHandler",
    "StepMetadata",
    "StepRegistry",
    "StepResult",
    "TriggerContext",
]


class StepRegistry:
    """Singleton registry of pipeline step handlers."""

    _handlers: dict[str, type[StepHandler]] = {}
    _instances: dict[str, StepHandler] = {}

    @classmethod
    def register(cls, handler_class: type[StepHandler]) -> type[StepHandler]:
        """Register a step handler class. Can be used as a decorator."""
        meta = handler_class.metadata()
        cls._handlers[meta.type_name] = handler_class
        cls._instances[meta.type_name] = handler_class()
        logger.debug("step_registered", type_name=meta.type_name)
        return handler_class

    @classmethod
    def get(cls, type_name: str) -> StepHandler | None:
        """Return the singleton handler instance for *type_name*."""
        return cls._instances.get(type_name)

    @classmethod
    def get_class(cls, type_name: str) -> type[StepHandler] | None:
        """Return the handler class for *type_name*."""
        return cls._handlers.get(type_name)

    @classmethod
    def all_metadata(cls) -> list[StepMetadata]:
        """Return metadata for all registered step types."""
        return [h.metadata() for h in cls._handlers.values()]

    @classmethod
    def type_names(cls) -> list[str]:
        """Return all registered step type names."""
        return list(cls._handlers.keys())

    @classmethod
    def discover(cls) -> None:
        """Auto-discover and register all step handlers in builtin/ and contrib/."""
        for package_name in ("backend.steps.builtin",):
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
                        "step_discovery_failed",
                        module=module_name,
                        error=str(e),
                    )
        # Also try contrib
        try:
            contrib = importlib.import_module("backend.steps.contrib")
            for _importer, module_name, _ispkg in pkgutil.iter_modules(
                contrib.__path__, contrib.__name__ + "."
            ):
                try:
                    importlib.import_module(module_name)
                except Exception as e:
                    logger.warning(
                        "step_discovery_failed",
                        module=module_name,
                        error=str(e),
                    )
        except ImportError:
            pass
