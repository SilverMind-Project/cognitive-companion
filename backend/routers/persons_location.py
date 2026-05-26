"""Person location endpoints (M4 unified location service)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.schemas.location import (
    CurrentLocationOut,
    LocationOverrideRequest,
    OccupantsResponse,
    PresenceHistoryResponse,
)
from backend.services.person_location.repositories import (
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService

router = APIRouter(prefix="/api/v1", tags=["persons-location"])
logger = get_logger(__name__)


def _get_service(db: Session = Depends(get_db)) -> PersonLocationService:
    return PersonLocationService(
        obs_repo=SqlAlchemyObservationRepository(db),
        seg_repo=SqlAlchemySegmentRepository(db),
    )


@router.get("/persons/{person_id}/location", response_model=CurrentLocationOut)
async def get_person_location(
    person_id: UUID,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
) -> CurrentLocationOut:
    """Return the current location of a person."""
    svc = _get_service(db)
    loc = await svc.where_is(person_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="No current location for this person")
    return CurrentLocationOut(
        person_id=loc.person_id,
        room_id=loc.room_id,
        room_name=loc.room_name,
        since=loc.since,
        entry_source=loc.entry_source,
        confidence=loc.confidence,
        is_inferred=loc.is_inferred,
    )


@router.get("/persons/{person_id}/presence-history", response_model=PresenceHistoryResponse)
async def get_presence_history(
    person_id: UUID,
    since: datetime | None = None,
    until: datetime | None = None,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
) -> PresenceHistoryResponse:
    """Return presence segments for a person in a time window."""
    now = datetime.now(UTC)
    _since = since or now.replace(hour=0, minute=0, second=0)
    _until = until or now
    svc = _get_service(db)
    segments = await svc.presence_history(person_id, _since, _until)
    return PresenceHistoryResponse(
        person_id=person_id,
        since=_since,
        until=_until,
        segments=[
            {
                "id": s.id,
                "person_id": s.person_id,
                "room_id": s.room_id,
                "room_name": str(s.metadata.get("room_name", "")),
                "entered_at": s.entered_at,
                "exited_at": s.exited_at,
                "entry_source": s.entry_source,
                "exit_source": s.exit_source,
                "confidence": s.confidence,
                "last_observed_at": s.last_observed_at,
                "superseded_by": s.superseded_by,
                "is_inferred": s.is_inferred,
            }
            for s in segments
        ],
    )


@router.get("/rooms/{room_id}/occupants", response_model=OccupantsResponse)
async def get_room_occupants(
    room_id: UUID,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
) -> OccupantsResponse:
    """Return currently-present persons in a room."""
    svc = _get_service(db)
    occupants = await svc.occupants_of(room_id)
    return OccupantsResponse(
        room_id=room_id,
        as_of=datetime.now(UTC),
        occupants=[
            CurrentLocationOut(
                person_id=o.person_id,
                room_id=o.room_id,
                room_name=o.room_name,
                since=o.since,
                entry_source=o.entry_source,
                confidence=o.confidence,
                is_inferred=o.is_inferred,
            )
            for o in occupants
        ],
    )


@router.get("/persons/{person_id}/dwell", response_model=dict)
async def get_person_dwell(
    person_id: UUID,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
) -> dict:
    """Return the currently-open segment for a person."""
    svc = _get_service(db)
    dwell = await svc.current_dwell(person_id)
    if dwell is None:
        return {"person_id": str(person_id), "dwell": None}
    return {
        "person_id": str(person_id),
        "dwell": {
            "id": str(dwell.id),
            "room_id": str(dwell.room_id),
            "entered_at": dwell.entered_at.isoformat(),
            "entry_source": dwell.entry_source,
            "is_inferred": dwell.is_inferred,
            "confidence": dwell.confidence,
        },
    }


@router.post(
    "/persons/{person_id}/location/override",
    status_code=status.HTTP_201_CREATED,
)
async def override_person_location(
    person_id: UUID,
    body: LocationOverrideRequest,
    _auth: AuthContext = Depends(require_permission("persons.write_overrides")),
    db: Session = Depends(get_db),
) -> dict:
    """Manually correct a person's location."""
    svc = _get_service(db)
    await svc.ingest_manual_override(
        person_id=person_id,
        room_id=body.room_id,
        entered_at=body.entered_at,
        note=body.note,
    )
    db.commit()
    return {"status": "ok", "person_id": str(person_id)}
