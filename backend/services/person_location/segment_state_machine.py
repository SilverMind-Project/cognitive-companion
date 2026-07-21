"""Pure decision functions for opening, closing, and superseding segments.

Each function takes the current persistence state plus an incoming event,
and returns a SegmentDecision describing the writes to perform. The service
layer applies the decision inside a transaction.

Why pure: every state transition is a test case.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from .types import EntrySource, ExitSource, PresenceSegment, SourceTag


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
    # Which source produced this event, for arbitration and per-source
    # evidence aging. None for event kinds that don't carry one
    # (TIMEOUT_TICK, IDENTITY_REVISION -- the latter preserves the
    # superseded segment's existing last_source via its metadata copy).
    source: SourceTag | None = None


@dataclass(frozen=True)
class SegmentWrite:
    segment: PresenceSegment


@dataclass(frozen=True)
class SegmentRefresh:
    """A same-room observation refreshing an open segment's evidence (M38).

    Unlike ``SegmentWrite`` (a new segment row), this is an in-place update:
    the segment id, room, and entry are unchanged; only freshness fields move.
    """

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
    refreshes: list[SegmentRefresh] = field(default_factory=list)
    closes: list[SegmentClose] = field(default_factory=list)
    supersedes: list[SegmentSupersede] = field(default_factory=list)


def decide(
    open_segment: PresenceSegment | None,
    event: IncomingEvent,
    inferred_dwell_max_s: float,
    quiet_gap_s: float | None = None,
) -> SegmentDecision:
    """Compute the segment writes for one incoming event.

    ``quiet_gap_s`` (M38 Part C) is only consulted for a TIMEOUT_TICK against
    a non-inferred (observed or manual) open segment: the per-source quiet
    gap resolved by the caller (``PersonLocationConfig.quiet_gap_s``) from
    the segment's ``metadata["last_source"]``. ``None`` means exempt (never
    ages here). Kept as a parameter rather than looked up inside this
    function so the state machine stays a pure function of its inputs.
    """

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
            # a same-room repeat now refreshes the open segment's
            # evidence instead of no-opping, so per-source quiet-gap aging
            # (Part C) and staleness handoff have a live last_observed_at to
            # measure from.
            #
            # Monotonicity guard: the room-change path's out-of-order guard
            # (source_arbitration.arbitrate) never sees a same-room event,
            # so this is the only protection here. Without it, a
            # slower-arriving source (e.g. world_tracker capture time vs.
            # a reCamera adapter's ingest-time stamp) could move
            # last_observed_at *backward*, regressing quiet-gap aging and
            # where_is staleness. An event no newer than what the segment
            # already has is a no-op, not a refresh.
            last_evidence_at = open_segment.last_observed_at or open_segment.entered_at
            if event.at <= last_evidence_at:
                return _noop()
            refreshed = replace(
                open_segment,
                last_observed_at=event.at,
                confidence=event.confidence,
                quality=event.quality,
                metadata={
                    **open_segment.metadata,
                    "last_source": event.source or open_segment.metadata.get("last_source"),
                },
            )
            return SegmentDecision(refreshes=[SegmentRefresh(refreshed)])
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
        if open_segment.is_inferred:
            age = (event.at - open_segment.entered_at).total_seconds()
            if age >= inferred_dwell_max_s:
                return SegmentDecision(
                    closes=[SegmentClose(open_segment.id, event.at, "timeout")],
                )
            return _noop()
        # observed (or manual) segment -- per-source quiet-gap
        # closure. No signal is emitted for this by the caller (tick):
        # inferred_dwell_exceeded stays exclusive to inferred segments.
        if quiet_gap_s is None:
            return _noop()
        last_evidence_at = open_segment.last_observed_at or open_segment.entered_at
        age = (event.at - last_evidence_at).total_seconds()
        if age >= quiet_gap_s:
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
    metadata = dict(event.metadata)
    if event.source is not None:
        # Seed last_source at segment open so the very first tick/refresh
        # after opening has a source to key per-source evidence aging on.
        metadata["last_source"] = event.source
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
        metadata=metadata,
    )
