"""Context filter plugin base class.

Each context filter type (room, time_range, day_of_week, etc.) implements
:class:`ContextFilter` and is auto-discovered by the :class:`FilterRegistry`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
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

    @abstractmethod
    def evaluate(
        self,
        config: dict,
        sensor: Any,
        now: datetime,
        db: Session | None = None,
    ) -> bool:
        """Return True if the context filter passes."""
        ...
