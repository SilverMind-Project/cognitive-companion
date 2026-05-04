"""Domain types for the PresenceService layer.

This module defines the core types used by all presence providers and the
service itself.  No provider or service logic lives here -- only data shapes
and the provider protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class PresenceStatus(StrEnum):
    """Current presence status of a household member."""

    PRESENT_ROOM = "present_room"
    PRESENT_HOME = "present_home"
    AWAY = "away"
    ASLEEP = "asleep"
    UNKNOWN = "unknown"
    STALE = "stale"


@dataclass(frozen=True)
class PresenceSource:
    """Metadata about a single provider's contribution to a snapshot."""

    name: str
    confidence: float
    weight: float = 1.0


@dataclass(frozen=True)
class PresenceSnapshot:
    """Fused presence result for one person at one point in time."""

    person_id: str
    status: PresenceStatus
    room_id: str | None
    room_name: str | None
    confidence: float
    last_seen_at: datetime | None
    dwell_minutes: float | None
    sources: tuple[PresenceSource, ...]
    inferred_at: datetime
    notes: str | None = None


@runtime_checkable
class PresenceProvider(Protocol):
    """Interface that all presence providers must implement."""

    name: str
    priority: int  # higher = preferred

    async def probe(self, person_id: str, at: datetime) -> PresenceSnapshot | None:
        """Return a snapshot candidate for *person_id*, or ``None``."""
        ...
