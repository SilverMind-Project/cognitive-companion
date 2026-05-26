"""Domain types for the unified person location service (M4).

All frozen dataclasses. No I/O, no validation logic (validation is at
the HTTP boundary via Pydantic schemas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

SourceTag = Literal["world_tracker", "recamera_vlm", "sensor", "manual"]
EntrySource = Literal["observed", "inferred_transit", "manual"]
ExitSource = Literal["observed", "inferred_transit", "contradicted", "manual", "timeout"]


@dataclass(frozen=True)
class FloorPoint:
    x_m: float
    y_m: float


@dataclass(frozen=True)
class LocationObservation:
    id: UUID
    person_id: UUID
    observed_at: datetime
    source: SourceTag
    source_ref: str | None = None
    floor_point: FloorPoint | None = None
    room_id: UUID | None = None
    confidence: float = 0.5
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PresenceSegment:
    id: UUID
    person_id: UUID
    room_id: UUID
    entered_at: datetime
    exited_at: datetime | None = None
    entry_source: EntrySource = "observed"
    exit_source: ExitSource | None = None
    confidence: float = 0.5
    last_observed_at: datetime | None = None
    superseded_by: UUID | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.exited_at is None

    @property
    def is_inferred(self) -> bool:
        return self.entry_source == "inferred_transit"

    @property
    def duration(self) -> timedelta | None:
        if self.exited_at is None:
            return None
        return self.exited_at - self.entered_at


@dataclass(frozen=True)
class CurrentLocation:
    person_id: UUID
    room_id: UUID
    room_name: str
    since: datetime
    entry_source: EntrySource
    confidence: float
    is_inferred: bool
