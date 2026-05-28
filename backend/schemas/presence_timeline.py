"""Presence timeline response schemas.

Contract: WTR1 §6 — person location rows use ``person_id``, not ``ph_id``.
PH id belongs in ``source_ref``. These schemas expose ``person_id`` for
caregiver-facing presence queries.

Contract: WTR1 §7 — ``room_id`` is an integer CC ``rooms.id`` value.
Room names are display labels only and must not be used for identity,
transition, or presence logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EntrySource = Literal["observed", "inferred_transit", "manual"]


class PresenceSegmentOut(BaseModel):
    segment_id: str
    person_id: str
    room_id: int
    room_name: str = ""
    entered_at: datetime | None = None
    exited_at: datetime | None = None
    dwell_seconds: float = 0.0
    entry_source: EntrySource = "observed"
    exit_source: str | None = None
    confidence: float = 0.5
    is_open: bool = False
    is_inferred: bool = False


class RoomTransitionOut(BaseModel):
    from_room_id: int | None = None
    from_room_name: str = ""
    to_room_id: int
    to_room_name: str = ""
    transitioned_at: datetime | None = None
    entry_source: EntrySource = "observed"


class SignalMarkerOut(BaseModel):
    signal_id: str
    signal_kind: str
    severity: str
    fired_at: datetime | None = None


class TimelineResponse(BaseModel):
    person_id: str
    since: datetime | None = None
    until: datetime | None = None
    segments: list[PresenceSegmentOut] = Field(default_factory=list)
    transitions: list[RoomTransitionOut] = Field(default_factory=list)
    signals: list[SignalMarkerOut] = Field(default_factory=list)


class RoomDwellTotal(BaseModel):
    room_id: int
    room_name: str = ""
    total_seconds: float = 0.0


class DwellsResponse(BaseModel):
    person_id: str
    window_since: datetime | None = None
    window_until: datetime | None = None
    dwells: list[RoomDwellTotal] = Field(default_factory=list)


class CurrentInEntry(BaseModel):
    person_id: str
    display_name: str = ""
    room_id: int | None = None
    room_name: str | None = None
    since: datetime | None = None
    dwell_seconds: float = 0.0
    entry_source: EntrySource | None = None
    is_inferred: bool = False
    last_observed_at: datetime | None = None


class CurrentlyInResponse(BaseModel):
    occupants: list[CurrentInEntry] = Field(default_factory=list)
