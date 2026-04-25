"""Context filter plugin base class.

Each context filter type (room, time_range, day_of_week, etc.) implements
:class:`ContextFilter` and is auto-discovered by the :class:`FilterRegistry`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session


@dataclass
class FilterMetadata:
    """Declarative metadata for a context filter type."""

    filter_type: str  # "room"
    display_name: str  # "Room"
    description: str
    config_schema: dict  # JSONSchema for config_json validation


class ContextFilter(ABC):
    """Base class for rule context filter plugins."""

    @classmethod
    @abstractmethod
    def metadata(cls) -> FilterMetadata:
        """Return filter type metadata."""
        ...

    def evaluate(
        self,
        config: dict,
        sensor: Any,
        now: datetime,
        db: Session | None = None,
        services: Any = None,
    ) -> bool | Awaitable[bool]:
        """Return True if the context filter passes.

        Args:
            config: Filter-specific configuration from the rule context.
            sensor: The Sensor that triggered the event.
            now: Current datetime (in the operator timezone).
            db: SQLAlchemy session for database queries.
            services: ServiceContainer with integration clients
                (e.g. semantic_memory_client). Defaults to None for
                backward compatibility with existing filters.
        """
        return True
