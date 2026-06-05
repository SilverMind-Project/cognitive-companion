"""Pure decision functions for opening, closing, and superseding segments.

Each function takes the current persistence state plus an incoming event,
and returns a SegmentDecision describing the writes to perform. The service
layer applies the decision inside a transaction.

Why pure: every state transition is a test case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from .types import EntrySource, ExitSource, PresenceSegment


class EventKind(StrEnum):
    OBSERVATION = "observation"
    TRANSIT_ENTER = "transit_enter"
    TRANSIT_EXIT = "transit_exit"
    TIMEOUT_TICK = "timeout_tick"
    IDENTITY_REVISION = "identity_revision"
    MANUAL_OVERRIDE = "manual_override"


@dataclass(frozen=True)
class IncomingEvent:
    kind: EventKind
    person_id: str
    room_id: int | None
    at: datetime
    confidence: float
    source_ref: str | None = None
    quality: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SegmentWrite:
    segment: PresenceSegment


@dataclass(frozen=True)
class SegmentClose:
    segment_id: UUID
    exited_at: datetime
    exit_source: ExitSource


@dataclass(frozen=True)
class SegmentSupersede:
    segment_id: UUID
    superseded_by: UUID


@dataclass(frozen=True)
class SegmentDecision:
    writes: list[SegmentWrite] = field(default_factory=list)
    closes: list[SegmentClose] = field(default_factory=list)
    supersedes: list[SegmentSupersede] = field(default_factory=list)


def decide(
    open_segment: PresenceSegment | None,
    event: IncomingEvent,
    inferred_dwell_max_s: float,
) -> SegmentDecision:
    """Compute the segment writes for one incoming event."""

    # No open segment: every event that has a room opens one.
    if open_segment is None:
        if event.kind in (
            EventKind.OBSERVATION,
            EventKind.TRANSIT_ENTER,
            EventKind.MANUAL_OVERRIDE,
        ):
            if event.room_id is None:
                return _noop()
            entry_source: EntrySource = (
                "observed"
                if event.kind == EventKind.OBSERVATION
                else "inferred_transit"
                if event.kind == EventKind.TRANSIT_ENTER
                else "manual"
            )
            return SegmentDecision(
                writes=[SegmentWrite(_new_segment(event, entry_source))],
            )
        return _noop()

    # Open segment exists. Cases by event kind.
    if event.kind == EventKind.OBSERVATION:
        if event.room_id == open_segment.room_id:
            return _noop()
        if event.room_id is None:
            return _noop()
        return SegmentDecision(
            writes=[SegmentWrite(_new_segment(event, "observed"))],
            closes=[SegmentClose(open_segment.id, event.at, "contradicted")],
        )

    if event.kind == EventKind.TRANSIT_ENTER:
        if event.room_id == open_segment.room_id:
            return _noop()
        if event.room_id is None:
            return _noop()
        return SegmentDecision(
            writes=[SegmentWrite(_new_segment(event, "inferred_transit"))],
            closes=[SegmentClose(open_segment.id, event.at, "inferred_transit")],
        )

    if event.kind == EventKind.TRANSIT_EXIT:
        if event.room_id is None:
            return _noop()
        if event.room_id == open_segment.room_id:
            return SegmentDecision(
                closes=[SegmentClose(open_segment.id, event.at, "inferred_transit")],
            )
        return SegmentDecision(
            writes=[SegmentWrite(_new_segment(event, "inferred_transit"))],
            closes=[SegmentClose(open_segment.id, event.at, "inferred_transit")],
        )

    if event.kind == EventKind.TIMEOUT_TICK:
        if not open_segment.is_inferred:
            return _noop()
        age = (event.at - open_segment.entered_at).total_seconds()
        if age >= inferred_dwell_max_s:
            return SegmentDecision(
                closes=[SegmentClose(open_segment.id, event.at, "timeout")],
            )
        return _noop()

    if event.kind == EventKind.MANUAL_OVERRIDE:
        return SegmentDecision(
            writes=[SegmentWrite(_new_segment(event, "manual"))],
            closes=[SegmentClose(open_segment.id, event.at, "manual")],
        )

    if event.kind == EventKind.IDENTITY_REVISION:
        new_person_id = str(event.metadata["new_person_id"])
        replacement = PresenceSegment(
            id=uuid4(),
            person_id=new_person_id,
            room_id=open_segment.room_id,
            entered_at=open_segment.entered_at,
            exited_at=open_segment.exited_at,
            entry_source=open_segment.entry_source,
            exit_source=open_segment.exit_source,
            confidence=open_segment.confidence,
            quality=open_segment.quality,
            last_observed_at=open_segment.last_observed_at,
            superseded_by=None,
            metadata={**open_segment.metadata, "revised_from": str(open_segment.id)},
        )
        return SegmentDecision(
            writes=[SegmentWrite(replacement)],
            supersedes=[SegmentSupersede(open_segment.id, replacement.id)],
        )

    return _noop()


def _noop() -> SegmentDecision:
    return SegmentDecision()


def _new_segment(event: IncomingEvent, entry_source: EntrySource) -> PresenceSegment:
    return PresenceSegment(
        id=uuid4(),
        person_id=event.person_id,
        room_id=event.room_id,  # type: ignore[arg-type]
        entered_at=event.at,
        exited_at=None,
        entry_source=entry_source,
        exit_source=None,
        confidence=event.confidence,
        quality=event.quality,
        last_observed_at=event.at if event.kind == EventKind.OBSERVATION else None,
        superseded_by=None,
        metadata=dict(event.metadata),
    )
