"""Unified Person Location Service (M4).

Single source of truth for "where is this person, and where have they been."
"""

from __future__ import annotations

from .config import PersonLocationConfig
from .service import PersonLocationService
from .types import (
    CurrentLocation,
    EntrySource,
    ExitSource,
    FloorPoint,
    LocationObservation,
    PresenceSegment,
    SourceTag,
)

__all__ = [
    "CurrentLocation",
    "EntrySource",
    "ExitSource",
    "FloorPoint",
    "LocationObservation",
    "PersonLocationConfig",
    "PersonLocationService",
    "PresenceSegment",
    "SourceTag",
]
