"""HTTP wire models for the unified location service."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# household_members.id is String(64); rooms.id is Integer. The observation
# row's own id and the segment's own id are UUID, as is superseded_by.
SourceTag = Literal["world_tracker", "face_sighting", "sensor", "manual"]
EntrySource = Literal["observed", "inferred_transit", "manual"]
ExitSource = Literal["observed", "inferred_transit", "contradicted", "manual", "timeout"]


class FloorPointWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x_m: float
    y_m: float


class LocationObservationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    person_id: str
    observed_at: datetime
    source: SourceTag
    source_ref: str | None = None
    floor_point: FloorPointWire | None = None
    room_id: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class PresenceSegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    person_id: str
    room_id: int
    room_name: str
    entered_at: datetime
    exited_at: datetime | None
    entry_source: EntrySource
    exit_source: ExitSource | None
    confidence: float = Field(ge=0.0, le=1.0)
    last_observed_at: datetime | None
    superseded_by: UUID | None
    is_inferred: bool


class CurrentLocationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: str
    room_id: int
    room_name: str
    since: datetime
    entry_source: EntrySource
    confidence: float
    is_inferred: bool


class OccupantsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_id: int
    as_of: datetime
    occupants: list[CurrentLocationOut]


class PresenceHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: str
    since: datetime
    until: datetime
    segments: list[PresenceSegmentOut]


class LocationOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: str
    room_id: int
    entered_at: datetime
    exited_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)
