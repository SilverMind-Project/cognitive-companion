"""Repositories for location observations and presence segments.

Protocol + InMemory triplet following project pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from math import floor
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.core.database import transaction
from backend.models.location_observation import LocationObservation as LOObs
from backend.models.presence_segment import PresenceSegment as PSeg

from .types import HeatmapBin, LocationObservation, PresenceSegment


class ObservationRepository(Protocol):
    async def insert(self, obs: LocationObservation) -> None: ...
    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]: ...
    async def list_for_source_ref(
        self, source_ref: str, since: datetime, until: datetime
    ) -> list[LocationObservation]: ...
    async def list_heatmap_bins(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        filter_start_hour: int | None = None,
        filter_end_hour: int | None = None,
    ) -> list[HeatmapBin]: ...


class SegmentRepository(Protocol):
    async def insert(self, seg: PresenceSegment) -> None: ...
    async def update(self, seg: PresenceSegment) -> None: ...
    async def get_by_id(self, segment_id: UUID) -> PresenceSegment | None: ...
    async def close_segment(
        self, segment_id: UUID, exited_at: datetime, exit_source: str
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
        closes: list[tuple[UUID, datetime, str]],
        supersedes: list[tuple[UUID, str | None]],
    ) -> None: ...


# ---------------------------------------------------------------------------
# In-memory implementations (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryObservationRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, LocationObservation] = {}

    async def insert(self, obs: LocationObservation) -> None:
        self._rows[obs.id] = obs

    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]:
        result = [
            o
            for o in self._rows.values()
            if o.person_id == person_id and since <= o.observed_at <= until
        ]
        result.sort(key=lambda o: o.observed_at, reverse=True)
        return result[:limit]

    async def list_for_source_ref(
        self, source_ref: str, since: datetime, until: datetime
    ) -> list[LocationObservation]:
        return [
            o
            for o in self._rows.values()
            if o.source_ref == source_ref and since <= o.observed_at <= until
        ]

    async def list_heatmap_bins(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        filter_start_hour: int | None = None,
        filter_end_hour: int | None = None,
    ) -> list[HeatmapBin]:
        relevant = [
            o
            for o in self._rows.values()
            if o.person_id == person_id
            and since <= o.observed_at < until
            and o.floor_point is not None
            and (filter_start_hour is None or o.observed_at.hour >= filter_start_hour)
            and (filter_end_hour is None or o.observed_at.hour < filter_end_hour)
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

    async def close_segment(self, segment_id: UUID, exited_at: datetime, exit_source: str) -> None:
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
        closes: list[tuple[UUID, datetime, str]],
        supersedes: list[tuple[UUID, str | None]],
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
                    last_observed_at=existing.last_observed_at,
                    superseded_by=superseded_by,
                    metadata=existing.metadata,
                )
                self._rows[seg_id] = existing


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

    async def list_for_person(
        self, person_id: str, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]:
        with transaction(self._db_factory) as db:
            rows = (
                db.execute(
                    select(LOObs)
                    .where(
                        LOObs.person_id == person_id,
                        LOObs.observed_at >= since,
                        LOObs.observed_at <= until,
                    )
                    .order_by(LOObs.observed_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        return [_obs_to_domain(r) for r in rows]

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

    async def list_heatmap_bins(
        self,
        person_id: str,
        since: datetime,
        until: datetime,
        filter_start_hour: int | None = None,
        filter_end_hour: int | None = None,
    ) -> list[HeatmapBin]:
        hour_clauses = ""
        if filter_start_hour is not None:
            hour_clauses += "\n              AND EXTRACT(HOUR FROM time_bucket_15m) >= :start_hour"
        if filter_end_hour is not None:
            hour_clauses += "\n              AND EXTRACT(HOUR FROM time_bucket_15m) < :end_hour"
        _SQL = text(f"""
            SELECT x_bin, y_bin, SUM(weight) AS weight
            FROM location_heatmaps_15m
            WHERE person_id = :person_id
              AND time_bucket_15m >= :since
              AND time_bucket_15m < :until{hour_clauses}
            GROUP BY x_bin, y_bin
            ORDER BY weight DESC
        """)
        params: dict = {"person_id": person_id, "since": since, "until": until}
        if filter_start_hour is not None:
            params["start_hour"] = filter_start_hour
        if filter_end_hour is not None:
            params["end_hour"] = filter_end_hour
        with transaction(self._db_factory) as db:
            rows = db.execute(_SQL, params).all()
        return [HeatmapBin(x_bin=float(r.x_bin), y_bin=float(r.y_bin), weight=int(r.weight)) for r in rows]


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

    async def close_segment(self, segment_id: UUID, exited_at: datetime, exit_source: str) -> None:
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
        closes: list[tuple[UUID, datetime, str]],
        supersedes: list[tuple[UUID, str | None]],
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


# ---------------------------------------------------------------------------
# Domain conversion helpers
# ---------------------------------------------------------------------------


def _obs_to_domain(row: LOObs) -> LocationObservation:
    from .types import FloorPoint

    fp = None
    if row.floor_x_m is not None and row.floor_y_m is not None:
        fp = FloorPoint(x_m=row.floor_x_m, y_m=row.floor_y_m)
    return LocationObservation(
        id=UUID(str(row.id)),
        person_id=str(row.person_id),
        observed_at=row.observed_at,
        source=row.source,
        source_ref=row.source_ref,
        floor_point=fp,
        room_id=int(row.room_id) if row.room_id is not None else None,
        confidence=row.confidence,
        metadata=row.metadata_json or {},
    )


def _seg_to_domain(row: PSeg) -> PresenceSegment:
    return PresenceSegment(
        id=UUID(str(row.id)),
        person_id=str(row.person_id),
        room_id=int(row.room_id),
        entered_at=row.entered_at,
        exited_at=row.exited_at,
        entry_source=row.entry_source,
        exit_source=row.exit_source,
        confidence=row.confidence,
        quality=float(getattr(row, "quality", 0.0) or 0.0),
        last_observed_at=row.last_observed_at,
        superseded_by=UUID(str(row.superseded_by)) if row.superseded_by else None,
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
