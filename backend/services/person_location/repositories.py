"""Repositories for location observations and presence segments (M4).

Protocol + InMemory triplet following project pattern.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.location_observation import LocationObservation as LOObs
from backend.models.presence_segment import PresenceSegment as PSeg

from .types import LocationObservation, PresenceSegment


class ObservationRepository(Protocol):
    async def insert(self, obs: LocationObservation) -> None: ...
    async def list_for_person(
        self, person_id: UUID, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]: ...
    async def list_for_source_ref(
        self, source_ref: str, since: datetime, until: datetime
    ) -> list[LocationObservation]: ...


class SegmentRepository(Protocol):
    async def insert(self, seg: PresenceSegment) -> None: ...
    async def update(self, seg: PresenceSegment) -> None: ...
    async def get_by_id(self, segment_id: UUID) -> PresenceSegment | None: ...
    async def close_segment(
        self, segment_id: UUID, exited_at: datetime, exit_source: str
    ) -> None: ...
    async def get_open(self, person_id: UUID) -> PresenceSegment | None: ...
    async def list_for_person(
        self, person_id: UUID, since: datetime, until: datetime
    ) -> list[PresenceSegment]: ...
    async def list_open_for_room(self, room_id: UUID) -> list[PresenceSegment]: ...
    async def list_overlapping(
        self, person_id: UUID, since: datetime, until: datetime
    ) -> list[PresenceSegment]: ...


# ---------------------------------------------------------------------------
# In-memory implementations (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryObservationRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, LocationObservation] = {}

    async def insert(self, obs: LocationObservation) -> None:
        self._rows[obs.id] = obs

    async def list_for_person(
        self, person_id: UUID, since: datetime, until: datetime, limit: int = 500
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
        self, segment_id: UUID, exited_at: datetime, exit_source: str
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
                last_observed_at=seg.last_observed_at,
                superseded_by=seg.superseded_by,
                metadata=seg.metadata,
            )

    async def get_open(self, person_id: UUID) -> PresenceSegment | None:
        for seg in self._rows.values():
            if seg.person_id == person_id and seg.is_open:
                return seg
        return None

    async def list_for_person(
        self, person_id: UUID, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        result = [
            s
            for s in self._rows.values()
            if s.person_id == person_id and s.entered_at >= since and s.entered_at <= until
        ]
        result.sort(key=lambda s: s.entered_at)
        return result

    async def list_open_for_room(self, room_id: UUID) -> list[PresenceSegment]:
        return [s for s in self._rows.values() if s.room_id == room_id and s.is_open]

    async def list_overlapping(
        self, person_id: UUID, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        return [
            s
            for s in self._rows.values()
            if s.person_id == person_id
            and s.entered_at <= until
            and (s.exited_at is None or s.exited_at >= since)
        ]


# ---------------------------------------------------------------------------
# SQLAlchemy implementations (production)
# ---------------------------------------------------------------------------


class SqlAlchemyObservationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    async def insert(self, obs: LocationObservation) -> None:
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
        self._db.add(row)
        self._db.flush()

    async def list_for_person(
        self, person_id: UUID, since: datetime, until: datetime, limit: int = 500
    ) -> list[LocationObservation]:
        rows = (
            self._db.execute(
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
        rows = (
            self._db.execute(
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


class SqlAlchemySegmentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    async def insert(self, seg: PresenceSegment) -> None:
        row = PSeg(
            id=seg.id,
            person_id=seg.person_id,
            room_id=seg.room_id,
            entered_at=seg.entered_at,
            exited_at=seg.exited_at,
            entry_source=seg.entry_source,
            exit_source=seg.exit_source,
            confidence=seg.confidence,
            last_observed_at=seg.last_observed_at,
            superseded_by=seg.superseded_by,
            metadata_json=dict(seg.metadata),
        )
        self._db.add(row)
        self._db.flush()

    async def update(self, seg: PresenceSegment) -> None:
        row = self._db.get(PSeg, seg.id)
        if row is None:
            return
        row.exited_at = seg.exited_at
        row.exit_source = seg.exit_source
        row.confidence = seg.confidence
        row.last_observed_at = seg.last_observed_at
        row.superseded_by = str(seg.superseded_by) if seg.superseded_by else None
        row.metadata_json = dict(seg.metadata)
        self._db.flush()

    async def get_by_id(self, segment_id: UUID) -> PresenceSegment | None:
        row = self._db.get(PSeg, segment_id)
        return _seg_to_domain(row) if row else None

    async def close_segment(
        self, segment_id: UUID, exited_at: datetime, exit_source: str
    ) -> None:
        row = self._db.get(PSeg, segment_id)
        if row is not None:
            row.exited_at = exited_at
            row.exit_source = exit_source
            self._db.flush()

    async def get_open(self, person_id: UUID) -> PresenceSegment | None:
        row = (
            self._db.execute(
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
        self, person_id: UUID, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        rows = (
            self._db.execute(
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

    async def list_open_for_room(self, room_id: UUID) -> list[PresenceSegment]:
        rows = (
            self._db.execute(
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

    async def list_overlapping(
        self, person_id: UUID, since: datetime, until: datetime
    ) -> list[PresenceSegment]:
        rows = (
            self._db.execute(
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


def _obs_to_domain(row: LOObs) -> LocationObservation:
    from .types import FloorPoint

    fp = None
    if row.floor_x_m is not None and row.floor_y_m is not None:
        fp = FloorPoint(x_m=row.floor_x_m, y_m=row.floor_y_m)
    return LocationObservation(
        id=UUID(str(row.id)),
        person_id=UUID(str(row.person_id)),
        observed_at=row.observed_at,
        source=row.source,
        source_ref=row.source_ref,
        floor_point=fp,
        room_id=UUID(str(row.room_id)) if row.room_id else None,
        confidence=row.confidence,
        metadata=row.metadata_json or {},
    )


def _seg_to_domain(row: PSeg) -> PresenceSegment:
    return PresenceSegment(
        id=UUID(str(row.id)),
        person_id=UUID(str(row.person_id)),
        room_id=UUID(str(row.room_id)),
        entered_at=row.entered_at,
        exited_at=row.exited_at,
        entry_source=row.entry_source,
        exit_source=row.exit_source,
        confidence=row.confidence,
        last_observed_at=row.last_observed_at,
        superseded_by=UUID(str(row.superseded_by)) if row.superseded_by else None,
        metadata=row.metadata_json or {},
    )
