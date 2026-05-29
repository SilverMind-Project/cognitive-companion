"""Generic plugin registry for auto-discovered step/channel/filter handlers.

Replaces the triplicate registry boilerplate in steps/, channels/, and filters/
with a single generic base class parameterized on the handler type and metadata type.
"""

from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from backend.core.logging import get_logger

logger = get_logger(__name__)

M = TypeVar("M")


class HasMetadata(ABC, Generic[M]):  # noqa: UP046
    """Mixin for plugin types that expose metadata via a classmethod."""

    @classmethod
    @abstractmethod
    def metadata(cls) -> M: ...


T_co = TypeVar("T_co", covariant=True, bound=HasMetadata[Any])


class PluginRegistry(Generic[T_co, M]):  # noqa: UP046
    """Generic singleton registry for discoverable plugin handlers.

    Subclasses set :attr:`_discovery_packages` and override
    :meth:`_key_from_metadata` to define how plugins are discovered and keyed.

    Usage::

        class StepRegistry(PluginRegistry[StepHandler, StepMetadata]):
            _discovery_packages = ("backend.steps.builtin",)

            @classmethod
            def _key_from_metadata(cls, meta: StepMetadata) -> str:
                return meta.type_name
    """

    _registry: dict[str, type[T_co]] = {}
    _instances: dict[str, T_co] = {}
    _discovery_packages: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own registry dicts — mutable class attributes
        # on a parent are shared by default, which would cause registries to
        # bleed into each other.
        cls._registry = {}
        cls._instances = {}

    # ── registration ──────────────────────────────────────────────────

    @classmethod
    def register(cls, handler_class: type[T_co]) -> type[T_co]:
        """Decorator: register a handler class and instantiate a singleton."""
        meta = handler_class.metadata()
        key = cls._key_from_metadata(meta)
        cls._registry[key] = handler_class
        cls._instances[key] = handler_class()
        logger.debug("plugin_registered", registry=cls.__name__, key=key)
        return handler_class

    @classmethod
    @abstractmethod
    def _key_from_metadata(cls, meta: M) -> str:
        """Extract the registry key from a metadata object."""

    # ── accessors ─────────────────────────────────────────────────────

    @classmethod
    def get(cls, key: str) -> T_co | None:
        """Return the singleton handler instance for *key*."""
        return cls._instances.get(key)

    @classmethod
    def all_metadata(cls) -> list[M]:
        """Return metadata for every registered handler."""
        return [h.metadata() for h in cls._registry.values()]

    @classmethod
    def all_names(cls) -> list[str]:
        """Return every registered key name."""
        return list(cls._registry.keys())

    # ── discovery ─────────────────────────────────────────────────────

    @classmethod
    def discover(cls) -> None:
        """Import every module under :attr:`_discovery_packages`.

        The act of importing triggers ``@<Registry>.register`` decorators,
        populating the registry.
        """
        for package_name in cls._discovery_packages:
            try:
                package = importlib.import_module(package_name)
            except ImportError:
                continue
            for _importer, module_name, _ispkg in pkgutil.iter_modules(
                package.__path__, package.__name__ + "."
            ):
                try:
                    importlib.import_module(module_name)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "plugin_discovery_failed",
                        registry=cls.__name__,
                        module=module_name,
                        error=str(e),
                    )
