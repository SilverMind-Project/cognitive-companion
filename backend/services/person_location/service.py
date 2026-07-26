"""PersonLocationService: single source of truth for person location.

All callers (filters, steps, UI) talk to this service; nothing reads
location_observations or presence_segments directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.schemas.cts_analytics import HeatmapBin as HeatmapBinSchema
from backend.schemas.cts_analytics import HeatmapEnvelope

from .config import PersonLocationConfig
from .repositories import ObservationRepository, SegmentRepository
from .segment_state_machine import (
    EventKind,
    IncomingEvent,
    SegmentDecision,
    decide,
)
from .source_arbitration import arbitrate
from .types import (
    BackfillDwellInput,
    BackfillIngestResult,
    CurrentLocation,
    DwellEpisode,
    FloorPoint,
    LocationObservation,
    PresenceSegment,
    RoomSegment,
    SourceTag,
)

logger = get_logger(__name__)


def _overlap_seconds(
    a_start: datetime, a_end: datetime | None, b_start: datetime, b_end: datetime
) -> float:
    """Seconds of overlap between segment ``[a_start, a_end)`` and ``[b_start, b_end)``.

    An open segment (``a_end is None``) is treated as extending to ``b_end``
    for this comparison -- an open segment overlapping a historical backfill
    window overlaps it for the entire window.
    """
    end = a_end if a_end is not None else b_end
    latest_start = max(a_start, b_start)
    earliest_end = min(end, b_end)
    return max(0.0, (earliest_end - latest_start).total_seconds())


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
        quality: float = 0.0,
        metadata: dict[str, object] | None = None,
        skip_segment: bool = False,
    ) -> None:
        """Ingest a single observation and update segments.

        ``skip_segment`` (M38 Part D): records the observation row for
        audit parity but never opens/moves a segment for it, even when
        ``room_id`` is given. Used for the reCamera unknown bucket (a
        merged pseudo-person, not an identity) so it never holds a room
        open or accumulates a fake dwell.
        """
        obs = LocationObservation(
            id=uuid4(),
            person_id=person_id,
            observed_at=observed_at,
            source=source,
            source_ref=source_ref,
            floor_point=floor_point,
            room_id=room_id,
            confidence=confidence,
            quality=quality,
            metadata=dict(metadata or {}),
        )
        await self._obs.insert(obs)

        if room_id is None or skip_segment:
            return

        open_seg = await self._seg.get_open(person_id)

        # arbitrate only when the incoming observation would change the
        # open segment's room -- a same-room repeat is a refresh, never
        # contested. Suppressing here (not in decide) keeps the state
        # machine pure; the observation row above is unaffected either way
        # (full-fidelity audit trail).
        if open_seg is not None and open_seg.room_id != room_id:
            last_source = open_seg.metadata.get("last_source")
            last_evidence_at = open_seg.last_observed_at or open_seg.entered_at
            verdict = arbitrate(
                incoming_source=source,
                incoming_at=observed_at,
                last_evidence_source=last_source,  # type: ignore[arg-type]
                last_evidence_at=last_evidence_at,
                staleness_s=self._cfg.arbitration_staleness_s,
            )
            if not verdict.allowed:
                logger.info(
                    "location_ingest_arbitrated",
                    person_id=person_id,
                    incoming_source=source,
                    last_evidence_source=last_source,
                    reason=verdict.reason,
                    incoming_room_id=room_id,
                    open_segment_room_id=open_seg.room_id,
                )
                return

        event = IncomingEvent(
            kind=EventKind.OBSERVATION,
            person_id=person_id,
            room_id=room_id,
            at=observed_at,
            confidence=confidence,
            quality=quality,
            source_ref=source_ref,
            source=source,
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
        event_time: datetime,
    ) -> None:
        """Handle a room transition event from tracking.room_transitions."""
        room_id = inside_room_id if direction == "enter" else outside_room_id
        event_kind = EventKind.TRANSIT_ENTER if direction == "enter" else EventKind.TRANSIT_EXIT

        open_seg = await self._seg.get_open(person_id)
        event = IncomingEvent(
            kind=event_kind,
            person_id=person_id,
            room_id=room_id,
            at=event_time,
            confidence=0.85,
            source_ref=transit_zone_id,
            # Room transitions are CTS-only (RoomTransitionSubscriber), so
            # this is always the dense, highest-priority source.
            source="world_tracker",
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
            source="manual",
            metadata=meta,
        )
        decision = decide(open_seg, event, self._cfg.inferred_dwell_max_s)
        await self._apply_decision(decision)

    async def apply_identity_revision(
        self,
        old_person_id: str,
        new_person_id: str | None,
        ph_id: str,
        revision_time: datetime,
    ) -> None:
        """Retroactively rewrite segments affected by an identity revision."""
        horizon = timedelta(seconds=self._cfg.revision_horizon_s)
        window_start = revision_time - horizon

        # Rewrite observations. Batched into one insert (see the segment
        # batching note below): a revision replay can touch a full horizon
        # window of observations, and committing one row at a time blocked
        # the event loop for the whole drain.
        affected_obs = await self._obs.list_for_source_ref(
            source_ref=ph_id,
            since=window_start,
            until=revision_time,
        )
        if new_person_id is not None:
            corrected_obs = [
                LocationObservation(
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
                for old_obs in affected_obs
            ]
            await self._obs.insert_many(corrected_obs)

        # Supersede affected segments. Only when the revision actually names a
        # new identity: with new_person_id is None, decide()'s IDENTITY_REVISION
        # branch falls back to `new_person_id or old_seg.person_id`, which
        # produces a same-person "replacement" that supersedes the original
        # with an identical copy -- a no-op in effect, but not in cost. On
        # stream redelivery of the same "no correction" revision this churned
        # unboundedly: list_overlapping (see below) doesn't exclude segments
        # already superseded, so every replay found *both* the original and
        # every prior replacement and copied all of them again, compounding
        # each redelivery (incident: 2.5M+ duplicate rows from one revision
        # replayed ~13 times after reclaim-timeout redelivery). Mirrors the
        # observation loop's existing `if new_person_id is not None:` guard.
        if new_person_id is not None:
            # A revision replay can touch hundreds of segments at once (e.g.
            # after downtime); committing per-segment made this a long
            # sequential drain of synchronous, un-offloaded DB commits that
            # starved the event loop for its whole duration (DL-M06 incident:
            # health checks timed out for minutes after a backlog replay).
            # Decide every segment first, then apply the merged batch in one
            # transaction.
            affected_segs = await self._seg.list_overlapping(
                person_id=old_person_id,
                since=window_start,
                until=revision_time + horizon,
            )
            batch = SegmentDecision()
            for old_seg in affected_segs:
                event = IncomingEvent(
                    kind=EventKind.IDENTITY_REVISION,
                    person_id=new_person_id,
                    room_id=None,
                    at=revision_time,
                    confidence=old_seg.confidence,
                    metadata={"new_person_id": new_person_id},
                )
                decision = decide(old_seg, event, self._cfg.inferred_dwell_max_s)
                batch.writes.extend(decision.writes)
                batch.refreshes.extend(decision.refreshes)
                batch.closes.extend(decision.closes)
                batch.supersedes.extend(decision.supersedes)
            await self._apply_decision(batch)

    async def ingest_backfill_segments(
        self,
        *,
        revision_id: str,
        person_id: str,
        dwells: list[BackfillDwellInput],
        range_start: datetime,
        range_end: datetime,
    ) -> BackfillIngestResult:
        """Insert closed presence segments for an ``inferred_backfill`` revision.

        Identity-continuity M05 (dated-corrected design): projects CTS room
        dwells for a previously-Unknown segment into the SSOT as **closed**
        historical segments (``entered_at``/``exited_at`` both set), so the
        one-open-segment-per-person invariant and ``where_is()`` are
        untouched by construction. No observation rows are inserted here --
        observations are the live audit feed, and fabricating historical rows
        would pollute ``bucketed_observations``/the heatmap with synthetic
        data; the dwell evidence lives in CTS.

        Idempotent under stream redelivery: if any segment already carries
        this ``revision_id``, the whole call is a no-op (the per-segment
        enforcement is the partial unique index on ``(backfill_revision_id,
        entered_at)`` in :meth:`SegmentRepository.insert_backfill_batch`;
        this early check just avoids redoing the room-resolution/overlap
        work on every redelivery).
        """
        if await self._seg.exists_for_backfill_revision(revision_id):
            return BackfillIngestResult(skipped_duplicate=len(dwells))

        candidates: list[PresenceSegment] = []
        dropped_unmapped_room = 0
        dropped_zero_length = 0
        overlap_skipped = 0

        for dwell in dwells:
            if dwell.room_id is None:
                dropped_unmapped_room += 1
                logger.warning(
                    "backfill_segment_dropped_unmapped_room",
                    revision_id=revision_id,
                    person_id=person_id,
                    room_name=dwell.room_name,
                )
                continue

            entered_at = max(dwell.entered_at, range_start)
            exited_at = min(dwell.exited_at, range_end)
            if exited_at <= entered_at:
                dropped_zero_length += 1
                continue

            overlapping = await self._seg.list_overlapping(person_id, entered_at, exited_at)
            non_backfill = [s for s in overlapping if s.backfill_revision_id is None]
            dwell_s = (exited_at - entered_at).total_seconds()
            overlap_s = sum(
                _overlap_seconds(s.entered_at, s.exited_at, entered_at, exited_at)
                for s in non_backfill
            )
            if dwell_s > 0 and (overlap_s / dwell_s) > 0.5:
                overlap_skipped += 1
                logger.info(
                    "backfill_segment_overlap_skipped",
                    revision_id=revision_id,
                    person_id=person_id,
                    room_id=dwell.room_id,
                    overlap_fraction=overlap_s / dwell_s,
                )
                continue

            candidates.append(
                PresenceSegment(
                    id=uuid4(),
                    person_id=person_id,
                    room_id=dwell.room_id,
                    entered_at=entered_at,
                    exited_at=exited_at,
                    entry_source="observed",
                    exit_source="observed",
                    confidence=dwell.confidence,
                    last_observed_at=exited_at,
                    backfill_revision_id=revision_id,
                    metadata={
                        "room_name": dwell.room_name,
                        "backfill_revision_id": revision_id,
                        "revision_kind": "inferred_backfill",
                    },
                )
            )

        inserted = 0
        if candidates:
            inserted = await self._seg.insert_backfill_batch(candidates)

        return BackfillIngestResult(
            inserted=inserted,
            dropped_unmapped_room=dropped_unmapped_room,
            dropped_zero_length=dropped_zero_length,
            overlap_skipped=overlap_skipped,
        )

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    async def where_is(self, person_id: str, at: datetime | None = None) -> CurrentLocation | None:
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
            quality=seg.quality,
            last_observed_at=seg.last_observed_at,
        )

    async def latest_floor_point(self, person_id: str, *, max_age_s: int = 30) -> FloorPoint | None:
        """Most recent observed floor point for a person, or None if stale/absent.

        Reads the newest ``location_observation`` with a floor point within
        ``max_age_s``. Room-level ``where_is`` behavior is unchanged.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=max_age_s)
        obs = await self._obs.latest_floor_point(person_id, since=cutoff)
        return obs.floor_point if obs is not None else None

    async def presence_history(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        """Return presence segments for a person in a time window."""
        return await self._seg.list_for_person(person_id, since, until)

    async def occupants_of(self, room_id: int, at: datetime | None = None) -> list[CurrentLocation]:
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
                    quality=seg.quality,
                    last_observed_at=seg.last_observed_at,
                )
            )
        return result

    async def current_dwell(self, person_id: str) -> PresenceSegment | None:
        """Return the currently-open segment (including inferred)."""
        return await self._seg.get_open(person_id)

    async def has_backfill_segments(self, revision_id: str) -> bool:
        """Whether any segment already carries this backfill ``revision_id``.

        Lets the M05 backfill projector skip its CTS dwell-fetch HTTP call
        entirely on stream redelivery, without reaching into
        ``SegmentRepository`` directly (never query the repo from outside
        this service).
        """
        return await self._seg.exists_for_backfill_revision(revision_id)

    async def get_heatmap(
        self,
        person_id: str,
        start_time: datetime,
        end_time: datetime,
        filter_start_minute: int | None = None,
        filter_end_minute: int | None = None,
    ) -> HeatmapEnvelope:
        """Return aggregated heatmap bins for a person over a time range.

        ``filter_start_minute`` and ``filter_end_minute`` (0-1439, minutes
        since *local* midnight) restrict which time-of-day buckets contribute
        to the density map. When ``start > end`` the window wraps past midnight
        (e.g. 22:00-03:00). The local timezone is the application timezone
        (``app.timezone``); stored buckets are UTC and converted in-query.
        """
        tz_name = settings.as_str("app.timezone")
        bins = await self._obs.list_heatmap_bins(
            person_id=person_id,
            since=start_time,
            until=end_time,
            tz_name=tz_name,
            filter_start_minute=filter_start_minute,
            filter_end_minute=filter_end_minute,
        )
        return HeatmapEnvelope(
            person_id=person_id,
            bins=[HeatmapBinSchema(x_m=b.x_bin, y_m=b.y_bin, weight=b.weight) for b in bins],
        )

    async def where_is_everyone(self) -> dict[str, CurrentLocation]:
        """Return current location for every person with an open segment."""
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
                quality=seg.quality,
                last_observed_at=seg.last_observed_at,
            )
        return result

    async def room_segments(
        self,
        person_id: str,
        start: datetime,
        end: datetime,
        *,
        now: datetime | None = None,
    ) -> tuple[RoomSegment, ...]:
        """Contiguous per-room presence segments overlapping ``[start, end]``.

        The one primitive the activity timeline, the daily room-time
        aggregator, and future dwell logic share. Superseded segments
        (rewritten by an identity revision) are excluded so callers never
        double-count a room-presence period under both the old and new
        identity. A still-open segment keeps ``exited_at=None`` (its truth);
        ``effective_exited_at`` gives minute-aggregation callers a clamped
        ``min(now, end)`` boundary without each reimplementing clock logic.
        """
        now = now or datetime.now(UTC)
        segs = await self._seg.list_overlapping(person_id, start, end)
        effective = sorted(
            (s for s in segs if s.superseded_by is None),
            key=lambda s: s.entered_at,
        )
        result: list[RoomSegment] = []
        for s in effective:
            effective_exited_at = s.exited_at if s.exited_at is not None else min(now, end)
            result.append(
                RoomSegment(
                    id=s.id,
                    person_id=s.person_id,
                    room_id=s.room_id,
                    room_name=str(s.metadata.get("room_name", "")),
                    entered_at=s.entered_at,
                    exited_at=s.exited_at,
                    effective_exited_at=effective_exited_at,
                    entry_source=s.entry_source,
                    exit_source=s.exit_source,
                    confidence=s.confidence,
                    quality=s.quality,
                    last_observed_at=s.last_observed_at,
                    metadata=dict(s.metadata),
                )
            )
        return tuple(result)

    async def dwell_episodes(
        self,
        person_id: str,
        room_id: int,
        start: datetime,
        end: datetime,
        *,
        now: datetime | None = None,
        merge_gap_s: int = 120,
    ) -> tuple[DwellEpisode, ...]:
        """Gap-merged dwell episodes in one room, built on :meth:`room_segments`.

        Built on top of ``room_segments`` rather than re-segmenting raw
        observations, for two reasons: (a) this package has exactly one
        segmentation, and ``room_segments`` already handles open-segment
        clamping and identity-revision supersession; (b) a room like a
        bathroom is typically **inferred** presence (a transit-zone entry;
        bathrooms have no cameras), which produces presence segments but
        zero observation rows, so an observation-based dwell computation
        would systematically report "no dwell" for exactly the room this is
        for. Segments are not filtered by ``entry_source``/``is_inferred``:
        an inferred-only episode is the normal case here, not a fallback.

        Two adjacent segments in ``room_id`` merge into one episode when the
        gap between one's ``effective_exited_at`` and the next's
        ``entered_at`` is at most ``merge_gap_s`` (a brief signal dropout
        should not split one continuous stay into two short ones). An
        episode's ``entered_at`` is its first segment's true start, never
        clamped to ``start``: a caller computing "did she dwell here at all"
        wants the full episode duration, not one truncated by an arbitrary
        window boundary chosen for the query.
        """
        segments = await self.room_segments(person_id, start, end, now=now)
        room_segs = sorted(
            (s for s in segments if s.room_id == room_id),
            key=lambda s: s.entered_at,
        )
        if not room_segs:
            return ()

        episodes: list[DwellEpisode] = []
        cur_start = room_segs[0].entered_at
        cur_end = room_segs[0].effective_exited_at
        for seg in room_segs[1:]:
            gap_s = (seg.entered_at - cur_end).total_seconds()
            if gap_s <= merge_gap_s:
                if seg.effective_exited_at > cur_end:
                    cur_end = seg.effective_exited_at
            else:
                episodes.append(
                    DwellEpisode(
                        entered_at=cur_start,
                        exited_at=cur_end,
                        minutes=(cur_end - cur_start).total_seconds() / 60,
                    )
                )
                cur_start = seg.entered_at
                cur_end = seg.effective_exited_at
        episodes.append(
            DwellEpisode(
                entered_at=cur_start,
                exited_at=cur_end,
                minutes=(cur_end - cur_start).total_seconds() / 60,
            )
        )
        return tuple(episodes)

    async def observations(
        self,
        person_id: str,
        start: datetime,
        end: datetime,
        *,
        sources: tuple[SourceTag, ...] | None = None,
        limit: int = 500,
    ) -> tuple[LocationObservation, ...]:
        """Raw observation events for ``person_id`` in ``[start, end]``.

        Newest-first, source-tagged, one row per ingested observation --
        this is the full-fidelity feed (world_tracker can ingest several
        rows a second), not an event-grade stream. Use
        ``bucketed_observations`` for a UI/timeline-appropriate downsample.
        ``sources`` restricts to the given source vocabulary
        (``world_tracker``, ``face_sighting``, ``sensor``, ``manual``); omit
        to return every source.
        """
        obs = await self._obs.list_for_person(person_id, start, end, limit=limit)
        if sources is not None:
            obs = [o for o in obs if o.source in sources]
        return tuple(obs)

    async def recent_observations(
        self,
        since: datetime,
        *,
        sources: tuple[SourceTag, ...] | None = None,
        limit: int = 20,
    ) -> tuple[LocationObservation, ...]:
        """Most recent observations across every person, since ``since``.

        Unlike ``observations()``, not scoped to a person -- backs HA
        presence-sensor correlation (M38 Part E), which discovers *which*
        person to correlate from recent camera activity rather than being
        told one up front.
        """
        obs = await self._obs.list_recent(since, sources=sources, limit=limit)
        return tuple(obs)

    async def bucketed_observations(
        self,
        person_id: str,
        start: datetime,
        end: datetime,
        *,
        sources: tuple[SourceTag, ...] | None = None,
        bucket_seconds: int = 120,
        limit: int = 500,
    ) -> tuple[LocationObservation, ...]:
        """Downsampled observation events for ``person_id`` in ``[start, end]``.

        One representative (most recent) observation per room per
        ``bucket_seconds`` window, newest-first. Backs the timeline's
        "sighting"-style entries: raw observations are per-frame, far
        denser than the legacy ``PersonSighting`` table this replaces, so
        a per-row event stream would drown out every other timeline source
        once merged. Bucketing happens before ``limit`` is applied, so
        (unlike ``observations``'s plain query LIMIT) coverage doesn't
        collapse to the newest slice of a wide window.
        """
        obs = await self._obs.bucketed_observations(
            person_id, start, end, bucket_seconds=bucket_seconds, limit=limit
        )
        if sources is not None:
            obs = [o for o in obs if o.source in sources]
        return tuple(obs)

    async def latest_observation(self, person_id: str) -> LocationObservation | None:
        """Most recent observation for a person, regardless of room or floor point.

        As of M38, a same-room repeat observation refreshes the open
        segment's ``last_observed_at``/``confidence``/``quality``
        (``segment_state_machine.decide``'s refresh branch), so
        ``where_is()``'s segment is no longer frozen at entry time either.
        This method remains the freshest raw observation timestamp and its
        resolved room name regardless of segment state -- use it for
        presence-provider staleness and "last known room" queries, which
        must still answer after a segment has closed or quiet-timed-out.
        """
        return await self._obs.latest_observation(person_id, since=datetime.min.replace(tzinfo=UTC))

    # ------------------------------------------------------------------
    # Inferred-dwell timeout evaluation
    # ------------------------------------------------------------------

    async def tick(self, now: datetime) -> list[dict[str, Any]]:
        """Evaluate timeout for every open segment.

        Inferred segments: unchanged camera-blind-dwell timeout. When a
        segment's age exceeds ``inferred_dwell_max_s``, the state machine
        closes it and this method appends an ``inferred_dwell_exceeded``
        signal dict to the return list. The caller is responsible for
        persisting those signals to the signal store.

        Observed (or manual) segments (M38 Part C): per-source quiet-gap
        closure. A segment whose last-recorded source has gone quiet longer
        than its configured gap (``PersonLocationConfig.quiet_gap_s``) is
        closed with ``exit_source="timeout"`` and **no signal** -- this is
        expected lifecycle for a sparse source, not a care event. A manual
        override, or a segment with no recorded source, never ages here.

        Returns a (possibly empty) list of signal dicts ready for
        ``SignalStore.upsert()``.
        """
        open_segments = await self._seg.list_all_open()
        signals: list[dict[str, Any]] = []

        for seg in open_segments:
            last_source = seg.metadata.get("last_source")
            quiet_gap_s = self._cfg.quiet_gap_s(
                last_source if isinstance(last_source, str) else None
            )

            event = IncomingEvent(
                kind=EventKind.TIMEOUT_TICK,
                person_id=seg.person_id,
                room_id=seg.room_id,
                at=now,
                confidence=seg.confidence,
            )
            decision = decide(seg, event, self._cfg.inferred_dwell_max_s, quiet_gap_s=quiet_gap_s)
            if not decision.closes:
                # No-op for this segment (quiet gap not yet exceeded, or
                # exempt): skip the write path entirely rather than opening
                # an empty transaction for every open segment on every tick.
                continue
            await self._apply_decision(decision)

            if not seg.is_inferred:
                # Quiet-gap closure: normal lifecycle, no signal (Part C).
                logger.info(
                    "person_location_quiet_closed",
                    person_id=seg.person_id,
                    room_id=seg.room_id,
                    last_source=last_source,
                    quiet_gap_s=quiet_gap_s,
                )
                continue

            dwell_s = (now - seg.entered_at).total_seconds()
            signal_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{seg.person_id}\x00inferred_dwell_exceeded"
                    f"\x00{seg.entered_at.isoformat()}\x00{now.isoformat()}",
                )
            )
            signals.append(
                {
                    "signal_id": signal_id,
                    "person_id": seg.person_id,
                    "signal_type": "inferred_dwell_exceeded",
                    "severity": "warning",
                    "window_start": seg.entered_at.isoformat(),
                    "window_end": now.isoformat(),
                    "value": dwell_s,
                    "baseline": self._cfg.inferred_dwell_max_s,
                    "z_score": None,
                    "context_json": None,
                    "algorithm_version": 1,
                }
            )
            logger.warning(
                "inferred_dwell_exceeded",
                person_id=seg.person_id,
                room_id=seg.room_id,
                dwell_s=dwell_s,
                threshold_s=self._cfg.inferred_dwell_max_s,
            )

        return signals

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _apply_decision(self, decision: SegmentDecision) -> None:
        """Apply a segment decision atomically."""
        for refresh in decision.refreshes:
            await self._seg.update(refresh.segment)
        await self._seg.apply_decision(
            writes=[sw.segment for sw in decision.writes],
            closes=[(sc.segment_id, sc.exited_at, sc.exit_source) for sc in decision.closes],
            supersedes=[(ss.segment_id, ss.superseded_by) for ss in decision.supersedes],
        )
