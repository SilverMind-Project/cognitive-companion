"""PresenceService domain layer.

Exports the core types and the service class.
"""

from __future__ import annotations

from backend.services.presence.service import PresenceService
from backend.services.presence.types import (
    PresenceProvider,
    PresenceSnapshot,
    PresenceSource,
    PresenceStatus,
)

__all__ = [
    "PresenceProvider",
    "PresenceService",
    "PresenceSnapshot",
    "PresenceSource",
    "PresenceStatus",
]
