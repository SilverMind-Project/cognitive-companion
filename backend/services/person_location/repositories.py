"""Repositories for location observations and presence segments.

Protocol + InMemory triplet following project pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from math import floor
from typing import Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.core.database import transaction
from backend.models.location_observation import LocationObservation as LOObs
from backend.models.presence_segment import PresenceSegment as PSeg
from backend.models.room import Room

from .types import (
    EntrySource,
    ExitSource,
    HeatmapBin,
    LocationObservation,
    PresenceSegment,
    SourceTag,
)


def minute_of_day_in_window(
    minute_of_day: int,
    start_minute: int | None,
    end_minute: int | None,
) -> bool:
    """Return whether a local minute-of-day (0-1439) falls inside the filter.

    Both bounds are minutes since local midnight. The window is half-open
    ``[start, end)``. When ``start_minute > end_minute`` the window wraps past
    midnight (e.g. 22:00-03:00), so the predicate becomes an OR. When either
    bound is ``None`` no time-of-day filtering is applied.
    """
    if start_minute is None or end_minute is None:
        return True
    if start_minute <= end_minute:
        return start_minute <= minute_of_day < end_minute
    return minute_of_day >= start_minute or minute_of_day < end_minute


class ObservationRepository(Protocol):
    async def insert(self, obs: LocationObservation) -> None: ...
    async def latest_floor_point(
        self, person_id: str, since: datetime
    ) -> LocationObservation | None: ...
    async def latest_observation(
        self, person_id: str, since: datetime
    ) -> LocationObservation | None: ...
    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]: ...
    async def bucketed_observations(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        bucket_seconds: int = 120,
        limit: int = 500,
    ) -> list[LocationObservation]: ...
    async def list_for_source_ref(
        self, source_ref: str, since: datetime, until: datetime
    ) -> list[LocationObservation]: ...
    async def list_recent(
        self,
        since: datetime,
        sources: tuple[SourceTag, ...] | None = None,
        limit: int = 20,
    ) -> list[LocationObservation]: ...
    async def list_heatmap_bins(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        tz_name: str = "UTC",
        filter_start_minute: int | None = None,
        filter_end_minute: int | None = None,
    ) -> list[HeatmapBin]: ...


class SegmentRepository(Protocol):
    async def insert(self, seg: PresenceSegment) -> None: ...
    async def update(self, seg: PresenceSegment) -> None: ...
    async def get_by_id(self, segment_id: UUID) -> PresenceSegment | None: ...
    async def close_segment(
        self, segment_id: UUID, exited_at: datetime, exit_source: ExitSource
    ) -> None: ...
    async def get_open(self, person_id: str) -> PresenceSegment | None: ...
    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]: ...
    async def list_open_for_room(self, room_id: int) -> list[PresenceSegment]: ...
    async def list_all_open(self) -> list[PresenceSegment]: ...
    async def list_overlapping(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]: ...
    async def apply_decision(
        self,
        writes: list[PresenceSegment],
        closes: list[tuple[UUID, datetime, ExitSource]],
        supersedes: list[tuple[UUID, UUID | None]],
    ) -> None: ...
    async def exists_for_backfill_revision(self, revision_id: str) -> bool: ...
    async def insert_backfill_batch(self, segments: list[PresenceSegment]) -> int: ...


# ---------------------------------------------------------------------------
# In-memory implementations (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryObservationRepository:
    def __init__(self, room_names: dict[int, str] | None = None) -> None:
        self._rows: dict[UUID, LocationObservation] = {}
        # Mirrors the SQL repo's rooms-table join in latest_observation;
        # tests inject the room_id -> name mapping they care about.
        self._room_names: dict[int, str] = room_names or {}

    async def insert(self, obs: LocationObservation) -> None:
        self._rows[obs.id] = obs

    async def latest_floor_point(
        self, person_id: str, since: datetime
    ) -> LocationObservation | None:
        matching = [
            o
            for o in self._rows.values()
            if o.person_id == person_id and o.observed_at >= since and o.floor_point is not None
        ]
        matching.sort(key=lambda o: o.observed_at, reverse=True)
        return matching[0] if matching else None

    async def latest_observation(
        self, person_id: str, since: datetime
    ) -> LocationObservation | None:
        matching = [
            o for o in self._rows.values() if o.person_id == person_id and o.observed_at >= since
        ]
        matching.sort(key=lambda o: o.observed_at, reverse=True)
        if not matching:
            return None
        latest = matching[0]
        # Re-resolve room_name from the injected map, mirroring the SQL
        # repo's rooms-table join: room_id is the source of truth, not
        # whatever a caller happened to set on the stored dataclass.
        room_name = self._room_names.get(latest.room_id) if latest.room_id is not None else None
        return replace(latest, room_name=room_name)

    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]:
        result = [
            o
            for o in self._rows.values()
            if o.person_id == person_id and since <= o.observed_at <= until
        ]
        result.sort(key=lambda o: o.observed_at, reverse=True)
        result = result[:limit]
        # Mirrors the SQL repo's rooms-table join (see below): resolve
        # room_name from the injected map for every row, not just the
        # single-row latest_observation path.
        return [
            replace(o, room_name=self._room_names.get(o.room_id) if o.room_id is not None else None)
            for o in result
        ]

    async def bucketed_observations(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        bucket_seconds: int = 120,
        limit: int = 500,
    ) -> list[LocationObservation]:
        matching = [
            o
            for o in self._rows.values()
            if o.person_id == person_id and since <= o.observed_at <= until
        ]
        # One representative (most recent) row per (room, time bucket),
        # mirroring the SQL repo's ROW_NUMBER-over-partition window.
        best: dict[tuple[int | None, int], LocationObservation] = {}
        for o in matching:
            bucket_index = int(o.observed_at.timestamp() // bucket_seconds)
            key = (o.room_id, bucket_index)
            current = best.get(key)
            if current is None or o.observed_at > current.observed_at:
                best[key] = o
        result = sorted(best.values(), key=lambda o: o.observed_at, reverse=True)[:limit]
        return [
            replace(o, room_name=self._room_names.get(o.room_id) if o.room_id is not None else None)
            for o in result
        ]

    async def list_for_source_ref(
        self, source_ref: str, since: datetime, until: datetime
    ) -> list[LocationObservation]:
        return [
            o
            for o in self._rows.values()
            if o.source_ref == source_ref and since <= o.observed_at <= until
        ]

    async def list_recent(
        self,
        since: datetime,
        sources: tuple[SourceTag, ...] | None = None,
        limit: int = 20,
    ) -> list[LocationObservation]:
        matching = [
            o
            for o in self._rows.values()
            if o.observed_at >= since and (sources is None or o.source in sources)
        ]
        matching.sort(key=lambda o: o.observed_at, reverse=True)
        return matching[:limit]

    async def list_heatmap_bins(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        tz_name: str = "UTC",
        filter_start_minute: int | None = None,
        filter_end_minute: int | None = None,
    ) -> list[HeatmapBin]:
        tz = ZoneInfo(tz_name)

        def _local_minute(o: LocationObservation) -> int:
            local = o.observed_at.astimezone(tz)
            return local.hour * 60 + local.minute

        relevant = [
            o
            for o in self._rows.values()
            if o.person_id == person_id
            and since <= o.observed_at < until
            and o.floor_point is not None
            and minute_of_day_in_window(_local_minute(o), filter_start_minute, filter_end_minute)
        ]
        bins: dict[tuple[float, float], int] = {}
        for o in relevant:
            fp = o.floor_point
            assert fp is not None
            key = (floor(fp.x_m / 0.5) * 0.5, floor(fp.y_m / 0.5) * 0.5)
            bins[key] = bins.get(key, 0) + 1
        return [HeatmapBin(x_bin=x, y_bin=y, weight=w) for (x, y), w in bins.items()]


class InMemorySegmentRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, PresenceSegment] = {}

    async def insert(self, seg: PresenceSegment) -> None:
        self._rows[seg.id] = seg

    async def update(self, seg: PresenceSegment) -> None:
        self._rows[seg.id] = seg

    async def get_by_id(self, segment_id: UUID) -> PresenceSegment | None:
        return self._rows.get(segment_id)

    async def close_segment(
        self, segment_id: UUID, exited_at: datetime, exit_source: ExitSource
    ) -> None:
        seg = self._rows.get(segment_id)
        if seg is not None:
            self._rows[segment_id] = PresenceSegment(
                id=seg.id,
                person_id=seg.person_id,
                room_id=seg.room_id,
                entered_at=seg.entered_at,
                exited_at=exited_at,
                entry_source=seg.entry_source,
                exit_source=exit_source,
                confidence=seg.confidence,
                quality=seg.quality,
                last_observed_at=seg.last_observed_at,
                superseded_by=seg.superseded_by,
                backfill_revision_id=seg.backfill_revision_id,
                metadata=seg.metadata,
            )

    async def get_open(self, person_id: str) -> PresenceSegment | None:
        for seg in self._rows.values():
            if seg.person_id == person_id and seg.is_open:
                return seg
        return None

    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        result = [
            s
            for s in self._rows.values()
            if s.person_id == person_id and s.entered_at >= since and s.entered_at <= until
        ]
        result.sort(key=lambda s: s.entered_at)
        return result

    async def list_open_for_room(self, room_id: int) -> list[PresenceSegment]:
        return [s for s in self._rows.values() if s.room_id == room_id and s.is_open]

    async def list_all_open(self) -> list[PresenceSegment]:
        return [s for s in self._rows.values() if s.is_open]

    async def list_overlapping(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        return [
            s
            for s in self._rows.values()
            if s.person_id == person_id
            and s.entered_at <= until
            and (s.exited_at is None or s.exited_at >= since)
        ]

    async def apply_decision(
        self,
        writes: list[PresenceSegment],
        closes: list[tuple[UUID, datetime, ExitSource]],
        supersedes: list[tuple[UUID, UUID | None]],
    ) -> None:
        for seg in writes:
            self._rows[seg.id] = seg
        for seg_id, exited_at, exit_source in closes:
            await self.close_segment(seg_id, exited_at, exit_source)
        for seg_id, superseded_by in supersedes:
            existing = self._rows.get(seg_id)
            if existing is not None:
                existing = PresenceSegment(
                    id=existing.id,
                    person_id=existing.person_id,
                    room_id=existing.room_id,
                    entered_at=existing.entered_at,
                    exited_at=existing.exited_at,
                    entry_source=existing.entry_source,
                    exit_source=existing.exit_source,
                    confidence=existing.confidence,
                    quality=existing.quality,
                    last_observed_at=existing.last_observed_at,
                    superseded_by=superseded_by,
                    backfill_revision_id=existing.backfill_revision_id,
                    metadata=existing.metadata,
                )
                self._rows[seg_id] = existing

    async def exists_for_backfill_revision(self, revision_id: str) -> bool:
        return any(s.backfill_revision_id == revision_id for s in self._rows.values())

    async def insert_backfill_batch(self, segments: list[PresenceSegment]) -> int:
        """Insert closed backfill segments, skipping ones already present.

        Mirrors the SQL repo's ``ON CONFLICT (backfill_revision_id,
        entered_at) DO NOTHING``: the uniqueness is on the pair, not the
        segment's own ``id``.
        """
        existing_keys: set[tuple[str | None, datetime]] = {
            (s.backfill_revision_id, s.entered_at)
            for s in self._rows.values()
            if s.backfill_revision_id is not None
        }
        inserted = 0
        for seg in segments:
            key = (seg.backfill_revision_id, seg.entered_at)
            if key in existing_keys:
                continue
            self._rows[seg.id] = seg
            existing_keys.add(key)
            inserted += 1
        return inserted


# ---------------------------------------------------------------------------
# SQLAlchemy implementations (production)
# ---------------------------------------------------------------------------


class SqlAlchemyObservationRepository:
    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory

    async def insert(self, obs: LocationObservation) -> None:
        with transaction(self._db_factory) as db:
            row = LOObs(
                id=obs.id,
                person_id=obs.person_id,
                observed_at=obs.observed_at,
                source=obs.source,
                source_ref=obs.source_ref,
                floor_x_m=obs.floor_point.x_m if obs.floor_point else None,
                floor_y_m=obs.floor_point.y_m if obs.floor_point else None,
                room_id=obs.room_id,
                confidence=obs.confidence,
                metadata_json=dict(obs.metadata),
            )
            db.add(row)
            db.flush()

    async def latest_floor_point(
        self, person_id: str, since: datetime
    ) -> LocationObservation | None:
        with transaction(self._db_factory) as db:
            row = (
                db.execute(
                    select(LOObs)
                    .where(
                        LOObs.person_id == person_id,
                        LOObs.observed_at >= since,
                        LOObs.floor_x_m.is_not(None),
                        LOObs.floor_y_m.is_not(None),
                    )
                    .order_by(LOObs.observed_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
        return _obs_to_domain(row) if row else None

    async def latest_observation(
        self, person_id: str, since: datetime
    ) -> LocationObservation | None:
        with transaction(self._db_factory) as db:
            row = (
                db.execute(
                    select(LOObs)
                    .where(
                        LOObs.person_id == person_id,
                        LOObs.observed_at >= since,
                    )
                    .order_by(LOObs.observed_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            room_name = None
            if row is not None and row.room_id is not None:
                room = db.get(Room, row.room_id)
                room_name = room.name if room is not None else None
        return _obs_to_domain(row, room_name=room_name) if row is not None else None

    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]:
        with transaction(self._db_factory) as db:
            rows = db.execute(
                select(LOObs, Room.name)
                .outerjoin(Room, LOObs.room_id == Room.id)
                .where(
                    LOObs.person_id == person_id,
                    LOObs.observed_at >= since,
                    LOObs.observed_at <= until,
                )
                .order_by(LOObs.observed_at.desc())
                .limit(limit)
            ).all()
        return [_obs_to_domain(r[0], room_name=r[1]) for r in rows]

    async def bucketed_observations(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        bucket_seconds: int = 120,
        limit: int = 500,
    ) -> list[LocationObservation]:
        """One representative (most recent) observation per room per
        ``bucket_seconds`` window, newest-first.

        world_tracker can call ``ingest_observation`` several times a
        second; a per-row event stream would be far denser than the legacy
        PersonSighting table this backs. The ROW_NUMBER() partition runs
        over every matching row before ``limit`` is applied, so (unlike a
        plain query LIMIT) a wide window's early history isn't silently
        dropped in favor of its newest slice.
        """
        with transaction(self._db_factory) as db:
            bucket_expr = (
                func.floor(func.extract("epoch", LOObs.observed_at) / bucket_seconds)
                * bucket_seconds
            )
            ranked = (
                select(
                    LOObs.id,
                    LOObs.person_id,
                    LOObs.observed_at,
                    LOObs.source,
                    LOObs.source_ref,
                    LOObs.floor_x_m,
                    LOObs.floor_y_m,
                    LOObs.room_id,
                    LOObs.confidence,
                    LOObs.metadata_json,
                    Room.name.label("room_name"),
                    func.row_number()
                    .over(
                        partition_by=(LOObs.room_id, bucket_expr),
                        order_by=LOObs.observed_at.desc(),
                    )
                    .label("rn"),
                )
                .outerjoin(Room, LOObs.room_id == Room.id)
                .where(
                    LOObs.person_id == person_id,
                    LOObs.observed_at >= since,
                    LOObs.observed_at <= until,
                )
                .subquery()
            )
            stmt = (
                select(ranked)
                .where(ranked.c.rn == 1)
                .order_by(ranked.c.observed_at.desc())
                .limit(limit)
            )
            rows = db.execute(stmt).all()
        return [_bucketed_row_to_domain(r) for r in rows]

    async def list_for_source_ref(
        self, source_ref: str, since: datetime, until: datetime
    ) -> list[LocationObservation]:
        with transaction(self._db_factory) as db:
            rows = (
                db.execute(
                    select(LOObs).where(
                        LOObs.source_ref == source_ref,
                        LOObs.observed_at >= since,
                        LOObs.observed_at <= until,
                    )
                )
                .scalars()
                .all()
            )
        return [_obs_to_domain(r) for r in rows]

    async def list_recent(
        self,
        since: datetime,
        sources: tuple[SourceTag, ...] | None = None,
        limit: int = 20,
    ) -> list[LocationObservation]:
        """Most recent observations across every person (M38 Part E).

        Backs HA presence-sensor correlation: unlike every other query here,
        this is deliberately not scoped to one person -- the caller doesn't
        know which person to look for yet, only which room just went
        occupied.
        """
        with transaction(self._db_factory) as db:
            stmt = (
                select(LOObs, Room.name)
                .outerjoin(Room, LOObs.room_id == Room.id)
                .where(LOObs.observed_at >= since)
            )
            if sources is not None:
                stmt = stmt.where(LOObs.source.in_(sources))
            rows = db.execute(stmt.order_by(LOObs.observed_at.desc()).limit(limit)).all()
        return [_obs_to_domain(r[0], room_name=r[1]) for r in rows]

    async def list_heatmap_bins(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        tz_name: str = "UTC",
        filter_start_minute: int | None = None,
        filter_end_minute: int | None = None,
    ) -> list[HeatmapBin]:
        # Local minute-of-day for each 15-minute bucket. ``time_bucket_15m`` is
        # TIMESTAMPTZ (UTC); ``AT TIME ZONE :tz`` rotates it to wall-clock time
        # in the application timezone so the filter is by *local* time of day.
        params: dict = {"person_id": person_id, "since": since, "until": until, "tz": tz_name}
        time_clause = ""
        if filter_start_minute is not None and filter_end_minute is not None:
            local_minute = (
                "(EXTRACT(HOUR FROM time_bucket_15m AT TIME ZONE :tz)::int * 60"
                " + EXTRACT(MINUTE FROM time_bucket_15m AT TIME ZONE :tz)::int)"
            )
            params["start_minute"] = filter_start_minute
            params["end_minute"] = filter_end_minute
            if filter_start_minute <= filter_end_minute:
                time_clause = (
                    f"\n              AND {local_minute} >= :start_minute"
                    f"\n              AND {local_minute} < :end_minute"
                )
            else:
                # Window wraps past midnight (e.g. 22:00-03:00).
                time_clause = (
                    f"\n              AND ({local_minute} >= :start_minute"
                    f" OR {local_minute} < :end_minute)"
                )
        _SQL = text(f"""
            SELECT x_bin, y_bin, SUM(weight) AS weight
            FROM location_heatmaps_15m
            WHERE person_id = :person_id
              AND time_bucket_15m >= :since
              AND time_bucket_15m < :until{time_clause}
            GROUP BY x_bin, y_bin
            ORDER BY weight DESC
        """)
        with transaction(self._db_factory) as db:
            rows = db.execute(_SQL, params).all()
        return [
            HeatmapBin(x_bin=float(r.x_bin), y_bin=float(r.y_bin), weight=int(r.weight))
            for r in rows
        ]


class SqlAlchemySegmentRepository:
    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory

    async def insert(self, seg: PresenceSegment) -> None:
        with transaction(self._db_factory) as db:
            _insert_seg(db, seg)

    async def update(self, seg: PresenceSegment) -> None:
        with transaction(self._db_factory) as db:
            _update_seg(db, seg)

    async def get_by_id(self, segment_id: UUID) -> PresenceSegment | None:
        with transaction(self._db_factory) as db:
            row = db.get(PSeg, segment_id)
        return _seg_to_domain(row) if row else None

    async def close_segment(
        self, segment_id: UUID, exited_at: datetime, exit_source: ExitSource
    ) -> None:
        with transaction(self._db_factory) as db:
            row = db.get(PSeg, segment_id)
            if row is not None:
                row.exited_at = exited_at
                row.exit_source = exit_source
                db.flush()

    async def get_open(self, person_id: str) -> PresenceSegment | None:
        with transaction(self._db_factory) as db:
            row = (
                db.execute(
                    select(PSeg).where(
                        PSeg.person_id == person_id,
                        PSeg.exited_at.is_(None),
                        PSeg.superseded_by.is_(None),
                    )
                )
                .scalars()
                .first()
            )
        return _seg_to_domain(row) if row else None

    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        with transaction(self._db_factory) as db:
            rows = (
                db.execute(
                    select(PSeg)
                    .where(
                        PSeg.person_id == person_id,
                        PSeg.entered_at >= since,
                        PSeg.entered_at <= until,
                    )
                    .order_by(PSeg.entered_at)
                )
                .scalars()
                .all()
            )
        return [_seg_to_domain(r) for r in rows]

    async def list_open_for_room(self, room_id: int) -> list[PresenceSegment]:
        with transaction(self._db_factory) as db:
            rows = (
                db.execute(
                    select(PSeg).where(
                        PSeg.room_id == room_id,
                        PSeg.exited_at.is_(None),
                        PSeg.superseded_by.is_(None),
                    )
                )
                .scalars()
                .all()
            )
        return [_seg_to_domain(r) for r in rows]

    async def list_all_open(self) -> list[PresenceSegment]:
        with transaction(self._db_factory) as db:
            rows = (
                db.execute(
                    select(PSeg).where(
                        PSeg.exited_at.is_(None),
                        PSeg.superseded_by.is_(None),
                    )
                )
                .scalars()
                .all()
            )
        return [_seg_to_domain(r) for r in rows]

    async def list_overlapping(
        self, person_id: str, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        with transaction(self._db_factory) as db:
            rows = (
                db.execute(
                    select(PSeg).where(
                        PSeg.person_id == person_id,
                        PSeg.entered_at <= until,
                        (PSeg.exited_at.is_(None)) | (PSeg.exited_at >= since),
                    )
                )
                .scalars()
                .all()
            )
        return [_seg_to_domain(r) for r in rows]

    async def apply_decision(
        self,
        writes: list[PresenceSegment],
        closes: list[tuple[UUID, datetime, ExitSource]],
        supersedes: list[tuple[UUID, UUID | None]],
    ) -> None:
        """Apply a segment decision atomically in a single transaction."""
        with transaction(self._db_factory) as db:
            for seg in writes:
                _insert_seg(db, seg)
            for seg_id, exited_at, exit_source in closes:
                row = db.get(PSeg, seg_id)
                if row is not None:
                    row.exited_at = exited_at
                    row.exit_source = exit_source
            for seg_id, superseded_by in supersedes:
                row = db.get(PSeg, seg_id)
                if row is not None:
                    row.superseded_by = str(superseded_by) if superseded_by else None
            db.flush()

    async def exists_for_backfill_revision(self, revision_id: str) -> bool:
        with transaction(self._db_factory) as db:
            row = (
                db.execute(select(PSeg.id).where(PSeg.backfill_revision_id == revision_id).limit(1))
                .scalars()
                .first()
            )
        return row is not None

    async def insert_backfill_batch(self, segments: list[PresenceSegment]) -> int:
        """Atomically insert closed backfill segments, skipping duplicates.

        Enforcement is the partial unique index on ``(backfill_revision_id,
        entered_at)``, not this method's own logic: ``ON CONFLICT DO
        NOTHING`` makes concurrent redelivery of the same revision race-safe
        even if two projector runs overlap. The ``RETURNING`` clause reports
        the true inserted count, since conflicting rows are silently skipped.
        """
        if not segments:
            return 0
        rows = [
            {
                "id": seg.id,
                "person_id": seg.person_id,
                "room_id": seg.room_id,
                "entered_at": seg.entered_at,
                "exited_at": seg.exited_at,
                "entry_source": seg.entry_source,
                "exit_source": seg.exit_source,
                "confidence": seg.confidence,
                "quality": seg.quality,
                "last_observed_at": seg.last_observed_at,
                "backfill_revision_id": seg.backfill_revision_id,
                "metadata_json": dict(seg.metadata),
            }
            for seg in segments
        ]
        stmt = (
            pg_insert(PSeg)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=["backfill_revision_id", "entered_at"],
                index_where=text("backfill_revision_id IS NOT NULL"),
            )
            .returning(PSeg.id)
        )
        with transaction(self._db_factory) as db:
            result = db.execute(stmt)
            inserted_ids = result.scalars().all()
        return len(inserted_ids)


# ---------------------------------------------------------------------------
# Domain conversion helpers
# ---------------------------------------------------------------------------


def _obs_to_domain(row: LOObs, room_name: str | None = None) -> LocationObservation:
    from .types import FloorPoint

    fp = None
    if row.floor_x_m is not None and row.floor_y_m is not None:
        fp = FloorPoint(x_m=row.floor_x_m, y_m=row.floor_y_m)
    return LocationObservation(
        id=UUID(str(row.id)),
        person_id=str(row.person_id),
        observed_at=row.observed_at,
        # The column is a plain String(32); every writer goes through the
        # Literal-typed domain type above, so the stored value is in-vocabulary
        # by construction. Asserted rather than re-validated on each row read.
        source=cast(SourceTag, row.source),
        source_ref=row.source_ref,
        floor_point=fp,
        room_id=int(row.room_id) if row.room_id is not None else None,
        confidence=row.confidence,
        metadata=row.metadata_json or {},
        room_name=room_name,
    )


def _bucketed_row_to_domain(row) -> LocationObservation:
    from .types import FloorPoint

    fp = None
    if row.floor_x_m is not None and row.floor_y_m is not None:
        fp = FloorPoint(x_m=row.floor_x_m, y_m=row.floor_y_m)
    return LocationObservation(
        id=UUID(str(row.id)),
        person_id=str(row.person_id),
        observed_at=row.observed_at,
        source=cast(SourceTag, row.source),
        source_ref=row.source_ref,
        floor_point=fp,
        room_id=int(row.room_id) if row.room_id is not None else None,
        confidence=row.confidence,
        metadata=row.metadata_json or {},
        room_name=row.room_name,
    )


def _seg_to_domain(row: PSeg) -> PresenceSegment:
    return PresenceSegment(
        id=UUID(str(row.id)),
        person_id=str(row.person_id),
        room_id=int(row.room_id),
        entered_at=row.entered_at,
        exited_at=row.exited_at,
        # Plain String(32) columns; in-vocabulary by construction (see
        # _obs_to_domain).
        entry_source=cast(EntrySource, row.entry_source),
        exit_source=cast("ExitSource | None", row.exit_source),
        confidence=row.confidence,
        quality=float(getattr(row, "quality", 0.0) or 0.0),
        last_observed_at=row.last_observed_at,
        superseded_by=UUID(str(row.superseded_by)) if row.superseded_by else None,
        backfill_revision_id=row.backfill_revision_id,
        metadata=row.metadata_json or {},
    )


def _insert_seg(db: Session, seg: PresenceSegment) -> None:
    row = PSeg(
        id=seg.id,
        person_id=seg.person_id,
        room_id=seg.room_id,
        entered_at=seg.entered_at,
        exited_at=seg.exited_at,
        entry_source=seg.entry_source,
        exit_source=seg.exit_source,
        confidence=seg.confidence,
        quality=seg.quality,
        last_observed_at=seg.last_observed_at,
        superseded_by=seg.superseded_by,
        backfill_revision_id=seg.backfill_revision_id,
        metadata_json=dict(seg.metadata),
    )
    db.add(row)
    db.flush()


def _update_seg(db: Session, seg: PresenceSegment) -> None:
    row = db.get(PSeg, seg.id)
    if row is None:
        return
    row.exited_at = seg.exited_at
    row.exit_source = seg.exit_source
    row.confidence = seg.confidence
    row.quality = seg.quality
    row.last_observed_at = seg.last_observed_at
    row.superseded_by = str(seg.superseded_by) if seg.superseded_by else None
    row.metadata_json = dict(seg.metadata)
    db.flush()
