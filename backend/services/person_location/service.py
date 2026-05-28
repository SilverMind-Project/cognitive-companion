"""PersonLocationService — single source of truth for person location (M4).

All callers (filters, steps, UI) talk to this service; nothing reads
location_observations or presence_segments directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from backend.core.logging import get_logger

from .config import PersonLocationConfig
from .repositories import ObservationRepository, SegmentRepository
from .segment_state_machine import (
    EventKind,
    IncomingEvent,
    SegmentDecision,
    decide,
)
from .types import (
    CurrentLocation,
    FloorPoint,
    LocationObservation,
    PresenceSegment,
    SourceTag,
)

logger = get_logger(__name__)


class PersonLocationService:
    """Unified person location: ingests observations, produces segments."""

    def __init__(
        self,
        obs_repo: ObservationRepository,
        seg_repo: SegmentRepository,
        config: PersonLocationConfig | None = None,
    ) -> None:
        self._obs = obs_repo
        self._seg = seg_repo
        self._cfg = config or PersonLocationConfig()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    async def ingest_observation(
        self,
        person_id: str,
        observed_at: datetime,
        source: SourceTag,
        source_ref: str | None = None,
        floor_point: FloorPoint | None = None,
        room_id: int | None = None,
        confidence: float = 0.5,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Ingest a single observation and update segments."""
        obs = LocationObservation(
            id=uuid4(),
            person_id=person_id,
            observed_at=observed_at,
            source=source,
            source_ref=source_ref,
            floor_point=floor_point,
            room_id=room_id,
            confidence=confidence,
            metadata=dict(metadata or {}),
        )
        await self._obs.insert(obs)

        if room_id is None:
            return

        open_seg = await self._seg.get_open(person_id)
        event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id=person_id,
            room_id=room_id,
            at=observed_at,
            confidence=confidence,
            source_ref=source_ref,
            metadata=dict(metadata or {}),
        )
        decision = decide(open_seg, event, self._cfg.inferred_dwell_max_s)
        await self._apply_decision(decision)

    async def ingest_room_transition(
        self,
        person_id: str,
        transit_zone_id: str,
        direction: str,
        inside_room_id: int,
        outside_room_id: int,
        floor_x_m: float,
        floor_y_m: float,
        event_time: datetime,
    ) -> None:
        """Handle a room transition event from tracking.room_transitions (M2)."""
        room_id = inside_room_id if direction == "enter" else outside_room_id
        event_kind = (
            EventKind.TRANSIT_ENTER if direction == "enter" else EventKind.TRANSIT_EXIT
        )

        open_seg = await self._seg.get_open(person_id)
        event = IncomingEvent(
            kind=event_kind,
            person_id=person_id,
            room_id=room_id,
            at=event_time,
            confidence=0.85,
            source_ref=transit_zone_id,
            metadata={"transit_zone_id": transit_zone_id, "direction": direction},
        )
        decision = decide(open_seg, event, self._cfg.inferred_dwell_max_s)
        await self._apply_decision(decision)

    async def ingest_manual_override(
        self,
        person_id: str,
        room_id: int,
        entered_at: datetime,
        note: str | None = None,
    ) -> None:
        """Apply a manual location override from a caregiver."""
        meta: dict[str, object] = {}
        if note:
            meta["note"] = note

        obs = LocationObservation(
            id=uuid4(),
            person_id=person_id,
            observed_at=entered_at,
            source="manual",
            room_id=room_id,
            confidence=1.0,
            metadata=meta,
        )
        await self._obs.insert(obs)

        open_seg = await self._seg.get_open(person_id)
        event = IncomingEvent(
            kind=EventKind.MANUAL_OVERRIDE,
            person_id=person_id,
            room_id=room_id,
            at=entered_at,
            confidence=1.0,
            metadata=meta,
        )
        decision = decide(open_seg, event, self._cfg.inferred_dwell_max_s)
        await self._apply_decision(decision)

    async def apply_identity_revision(
        self,
        old_person_id: str,
        new_person_id: str | None,
        global_track_id: str,
        revision_time: datetime,
    ) -> None:
        """Retroactively rewrite segments affected by an identity revision."""
        horizon = timedelta(seconds=self._cfg.revision_horizon_s)
        window_start = revision_time - horizon

        # Rewrite observations.
        affected_obs = await self._obs.list_for_source_ref(
            source_ref=global_track_id,
            since=window_start,
            until=revision_time,
        )
        for old_obs in affected_obs:
            if new_person_id is None:
                continue
            corrected = LocationObservation(
                id=uuid4(),
                person_id=new_person_id,
                observed_at=old_obs.observed_at,
                source=old_obs.source,
                source_ref=old_obs.source_ref,
                floor_point=old_obs.floor_point,
                room_id=old_obs.room_id,
                confidence=old_obs.confidence,
                metadata={
                    **old_obs.metadata,
                    "revised_from_person_id": str(old_obs.person_id),
                },
            )
            await self._obs.insert(corrected)

        # Supersede affected segments.
        affected_segs = await self._seg.list_overlapping(
            person_id=old_person_id,
            since=window_start,
            until=revision_time + horizon,
        )
        for old_seg in affected_segs:
            event = IncomingEvent(
                kind=EventKind.IDENTITY_REVISION,
                person_id=new_person_id or old_seg.person_id,
                room_id=None,
                at=revision_time,
                confidence=old_seg.confidence,
                metadata={
                    "new_person_id": str(new_person_id or old_seg.person_id),
                },
            )
            decision = decide(old_seg, event, self._cfg.inferred_dwell_max_s)
            await self._apply_decision(decision)

    async def ingest_ph_continuation(
        self,
        predecessor_person_id: str,
        successor_ph_id: str,
        predecessor_room_id: int,
        predecessor_entered_at: datetime,
        handoff_time: datetime,
    ) -> None:
        """Stitch a presumed-presence link across a PH closure (M1 continuation).

        When a PH closes and a new one spawns nearby within the handoff window,
        the predecessor's inferred segment carries forward to the successor.
        """
        open_seg = await self._seg.get_open(predecessor_person_id)
        if open_seg is None or not open_seg.is_inferred:
            return

        from .segment_state_machine import EventKind, IncomingEvent

        event = IncomingEvent(
            kind=EventKind.TRANSIT_ENTER,
            person_id=predecessor_person_id,
            room_id=predecessor_room_id,
            at=handoff_time,
            confidence=0.85,
            source_ref=successor_ph_id,
            metadata={
                "continuation_from": str(predecessor_person_id),
                "successor_ph_id": successor_ph_id,
            },
        )
        decision = decide(open_seg, event, self._cfg.inferred_dwell_max_s)
        await self._apply_decision(decision)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    async def where_is(
        self, person_id: str, at: datetime | None = None
    ) -> CurrentLocation | None:
        """Return the current location of a person."""
        seg = await self._seg.get_open(person_id)
        if seg is None:
            return None
        return CurrentLocation(
            person_id=seg.person_id,
            room_id=seg.room_id,
            room_name=str(seg.metadata.get("room_name", "")),
            since=seg.entered_at,
            entry_source=seg.entry_source,
            confidence=seg.confidence,
            is_inferred=seg.is_inferred,
        )

    async def presence_history(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        """Return presence segments for a person in a time window."""
        return await self._seg.list_for_person(person_id, since, until)

    async def occupants_of(
        self, room_id: int, at: datetime | None = None
    ) -> list[CurrentLocation]:
        """Return currently-present persons in a room."""
        segments = await self._seg.list_open_for_room(room_id)
        result: list[CurrentLocation] = []
        for seg in segments:
            result.append(
                CurrentLocation(
                    person_id=seg.person_id,
                    room_id=seg.room_id,
                    room_name=str(seg.metadata.get("room_name", "")),
                    since=seg.entered_at,
                    entry_source=seg.entry_source,
                    confidence=seg.confidence,
                    is_inferred=seg.is_inferred,
                )
            )
        return result

    async def current_dwell(self, person_id: str) -> PresenceSegment | None:
        """Return the currently-open segment (including inferred)."""
        return await self._seg.get_open(person_id)

    async def where_is_everyone(self) -> dict[str, CurrentLocation]:
        """Return current location for every person with an open segment (WTR4)."""
        all_open = await self._seg.list_all_open()
        result: dict[str, CurrentLocation] = {}
        for seg in all_open:
            result[seg.person_id] = CurrentLocation(
                person_id=seg.person_id,
                room_id=seg.room_id,
                room_name=str(seg.metadata.get("room_name", "")),
                since=seg.entered_at,
                entry_source=seg.entry_source,
                confidence=seg.confidence,
                is_inferred=seg.is_inferred,
            )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _apply_decision(self, decision: SegmentDecision) -> None:
        for sw in decision.writes:
            await self._seg.insert(sw.segment)
        for sc in decision.closes:
            await self._seg.close_segment(
                sc.segment_id, sc.exited_at, sc.exit_source
            )
        for ss in decision.supersedes:
            existing = await self._seg.get_by_id(ss.segment_id)
            if existing is not None:
                updated = PresenceSegment(
                    id=existing.id,
                    person_id=existing.person_id,
                    room_id=existing.room_id,
                    entered_at=existing.entered_at,
                    exited_at=existing.exited_at,
                    entry_source=existing.entry_source,
                    exit_source=existing.exit_source,
                    confidence=existing.confidence,
                    last_observed_at=existing.last_observed_at,
                    superseded_by=ss.superseded_by,
                    metadata=existing.metadata,
                )
                await self._seg.update(updated)
