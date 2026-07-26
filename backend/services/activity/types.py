"""Domain types for the ActivityService.

Frozen dataclasses mirroring the data the existing services return.
Match fields exactly so step migrations are a one-line swap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ActivityRecord:
    """A single activity record for a person.

    Mirrors the columns on :class:`~backend.models.person.PersonActivity`.
    """

    id: int | None
    person_id: str
    activity_type: str
    room_id: int | None
    room_name: str | None
    confidence: float
    source_event_id: int | None
    metadata_json: dict | None
    duration_minutes: int | None
    session_id: str | None
    detected_at: datetime | None


@dataclass(frozen=True)
class SessionRecord:
    """An activity session (open or closed).

    Mirrors the columns on :class:`~backend.models.person.ActivitySession`.
    """

    session_id: str
    person_id: str
    activity_type: str
    room_name: str | None
    opened_at: datetime
    closed_at: datetime | None
    duration_minutes: int | None
    status: str
    closed_via: str | None
    timeout_minutes: int | None
    source: str = "vision_inferred"
    """How the row was produced (``ActivitySourceEnum``); the evidence grade."""
    confidence: float = 0.0
    was_existing: bool = False
