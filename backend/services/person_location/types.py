"""Domain types for the unified person location service.

All frozen dataclasses. No I/O, no validation logic (validation is at
the HTTP boundary via Pydantic schemas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

SourceTag = Literal["world_tracker", "face_sighting", "sensor", "manual"]
EntrySource = Literal["observed", "inferred_transit", "manual"]
ExitSource = Literal["observed", "inferred_transit", "contradicted", "manual", "timeout"]


def is_unknown_bucket(person_id: str) -> bool:
    """The literal unidentified bucket: a merged pseudo-person, not an identity.

    Named guests enrolled via the visitor admin surface (identity-continuity
    M07) arrive as real member ids and are not affected by this check. Every
    SSOT consumer that treats a person_id as a real, correlatable identity
    (segment writes, HA-sensor correlation, identity assertions) must skip
    this bucket: it is a merged pseudo-person shared by every unidentified
    visitor, so any segment/correlation opened for it would churn across
    all of them at once (W7).
    """
    return person_id == "unknown" or person_id.startswith("unknown_")


@dataclass(frozen=True)
class FloorPoint:
    x_m: float
    y_m: float


@dataclass(frozen=True)
class LocationObservation:
    # person_id is household_members.id (String(64)); room_id is rooms.id (Integer).
    # The observation row itself is UUID-keyed.
    id: UUID
    person_id: str
    observed_at: datetime
    source: SourceTag
    source_ref: str | None = None
    floor_point: FloorPoint | None = None
    room_id: int | None = None
    confidence: float = 0.5
    quality: float = 0.0  # PH mean_quality from CTS snapshot
    metadata: dict[str, object] = field(default_factory=dict)
    # Resolved from the rooms table by ObservationRepository.latest_observation
    # only; every other read path leaves this None (room_id is the durable
    # identity, this is a display-name convenience for that one query).
    room_name: str | None = None


@dataclass(frozen=True)
class PresenceSegment:
    id: UUID
    person_id: str
    room_id: int
    entered_at: datetime
    exited_at: datetime | None = None
    entry_source: EntrySource = "observed"
    exit_source: ExitSource | None = None
    confidence: float = 0.5
    quality: float = 0.0  # PH mean_quality from CTS wire
    last_observed_at: datetime | None = None
    superseded_by: UUID | None = None
    # set only for segments inserted by the Unknown backfill
    # backfill projector; None for every ordinary segment. Backed by a
    # partial unique index on (backfill_revision_id, entered_at).
    backfill_revision_id: str | None = None
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
class RoomSegment:
    """A contiguous per-room presence segment, resolved for read consumers.

    Wraps a ``PresenceSegment`` with its room name and, for a still-open
    segment, an ``effective_exited_at`` clamped to ``min(now, query_end)`` so
    minute-aggregation callers never need their own clock logic.
    """

    id: UUID
    person_id: str
    room_id: int
    room_name: str
    entered_at: datetime
    exited_at: datetime | None  # None means still open
    effective_exited_at: datetime
    entry_source: EntrySource
    exit_source: ExitSource | None
    confidence: float
    quality: float
    last_observed_at: datetime | None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.exited_at is None


@dataclass(frozen=True)
class DwellEpisode:
    """One gap-merged dwell episode in a single room, built from ``room_segments``.

    ``entered_at`` keeps the first constituent segment's true start (never
    clamped to the query window: a shower proxy wants full episode duration,
    not a truncated one), while ``exited_at`` is each segment's own
    ``effective_exited_at`` (already clamped to ``min(now, query_end)`` for a
    still-open segment).
    """

    entered_at: datetime
    exited_at: datetime
    minutes: float


@dataclass(frozen=True)
class HeatmapBin:
    x_bin: float
    y_bin: float
    weight: int


@dataclass(frozen=True)
class CurrentLocation:
    person_id: str
    room_id: int
    room_name: str
    since: datetime
    entry_source: EntrySource
    confidence: float
    is_inferred: bool
    quality: float = 0.0  # PH mean_quality; 0.0 = no data yet
    last_observed_at: datetime | None = None  # for staleness_seconds in envelope


@dataclass(frozen=True)
class BackfillDwellInput:
    """One CTS room dwell to project as a closed presence segment (M05).

    ``room_id`` is None when the dwell's ``room_name`` could not be resolved
    against the ``rooms`` table; the caller drops it rather than fabricating
    a room. ``confidence`` is the dwell's own ``entry_confidence`` from the
    CTS ``/internal/trajectory/dwells`` response -- the wire-level
    ``IdentityRevision`` carries no revision-level confidence field.
    """

    room_id: int | None
    room_name: str
    entered_at: datetime
    exited_at: datetime
    confidence: float


@dataclass(frozen=True)
class BackfillIngestResult:
    """Outcome counts from :meth:`PersonLocationService.ingest_backfill_segments`."""

    inserted: int = 0
    skipped_duplicate: int = 0
    dropped_unmapped_room: int = 0
    dropped_zero_length: int = 0
    overlap_skipped: int = 0
