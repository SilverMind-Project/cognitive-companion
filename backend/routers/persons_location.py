"""Person location endpoints (unified location service, envelope-shaped responses)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.person import HouseholdMember
from backend.schemas.cts_envelopes import (
    PersonLocationEnvelope,
    RoomOccupancyEnvelope,
)
from backend.schemas.location import (
    LocationOverrideRequest,
    PresenceHistoryResponse,
)
from backend.services.person_location.repositories import (
    SqlAlchemyObservationRepository,
    SqlAlchemySegmentRepository,
)
from backend.services.person_location.service import PersonLocationService
from backend.services.person_location.types import CurrentLocation

router = APIRouter(prefix="/api/v1", tags=["persons-location"])
logger = get_logger(__name__)


def _get_service(db: Session = Depends(get_db)) -> PersonLocationService:
    return PersonLocationService(
        obs_repo=SqlAlchemyObservationRepository(db),
        seg_repo=SqlAlchemySegmentRepository(db),
    )


def _lookup_display_name(person_id: str, db: Session) -> str:
    """Fetch display name from household_members; return empty string if not found."""
    member = db.get(HouseholdMember, person_id)
    return member.name if member else ""


def _display_names_for(person_ids: list[str], db: Session) -> dict[str, str]:
    """Batch-fetch display names; avoids N+1 on the batch endpoint."""
    rows = (
        db.execute(select(HouseholdMember).where(HouseholdMember.id.in_(person_ids)))
        .scalars()
        .all()
    )
    return {m.id: m.name for m in rows}


def _loc_to_envelope(
    loc: CurrentLocation,
    *,
    display_name: str,
    now: datetime,
) -> PersonLocationEnvelope:
    return PersonLocationEnvelope.from_current_location(
        loc,
        display_name=display_name,
        now=now,
    )


# ---------------------------------------------------------------------------
# GET /persons/{person_id}/location  (U2: shaped to PersonLocationEnvelope)
# ---------------------------------------------------------------------------


@router.get("/persons/{person_id}/location", response_model=PersonLocationEnvelope)
async def get_person_location(
    person_id: str,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
    svc: PersonLocationService = Depends(_get_service),
) -> PersonLocationEnvelope:
    """Return the current location of a person.

    U2: response is a PersonLocationEnvelope (strict superset of the pre-U2
    CurrentLocationOut shape — all pre-U2 fields are present; new fields
    confidence/quality/staleness_seconds/source/display_name are added).
    """
    loc = await svc.where_is(person_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="No current location for this person")
    return _loc_to_envelope(
        loc,
        display_name=_lookup_display_name(person_id, db),
        now=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# GET /persons/locations  (U2: new batch endpoint, backed by where_is_everyone)
# ---------------------------------------------------------------------------


@router.get("/persons/locations", response_model=list[PersonLocationEnvelope])
async def get_all_person_locations(
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
    svc: PersonLocationService = Depends(_get_service),
) -> list[PersonLocationEnvelope]:
    """Return current location for every household member with an open segment.

    U2/D1: one endpoint for "where is everyone" — fetches the whole household
    in one call. U4 uses this instead of per-person fetches.
    """
    everyone = await svc.where_is_everyone()
    if not everyone:
        return []

    now = datetime.now(UTC)
    display_names = _display_names_for(list(everyone.keys()), db)
    return [
        _loc_to_envelope(loc, display_name=display_names.get(pid, ""), now=now)
        for pid, loc in everyone.items()
    ]


# ---------------------------------------------------------------------------
# GET /persons/{person_id}/presence-history  (unchanged shape)
# ---------------------------------------------------------------------------


@router.get("/persons/{person_id}/presence-history", response_model=PresenceHistoryResponse)
async def get_presence_history(
    person_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    svc: PersonLocationService = Depends(_get_service),
) -> PresenceHistoryResponse:
    """Return presence segments for a person in a time window."""
    now = datetime.now(UTC)
    _since = since or now.replace(hour=0, minute=0, second=0)
    _until = until or now
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


# ---------------------------------------------------------------------------
# GET /rooms/{room_id}/occupants  (U2: shaped to RoomOccupancyEnvelope)
# ---------------------------------------------------------------------------


@router.get("/rooms/{room_id}/occupants", response_model=RoomOccupancyEnvelope)
async def get_room_occupants(
    room_id: int,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    db: Session = Depends(get_db),
    svc: PersonLocationService = Depends(_get_service),
) -> RoomOccupancyEnvelope:
    """Return currently-present persons in a room.

    U2: response is a RoomOccupancyEnvelope. This is a strict superset of
    the pre-U2 OccupantsResponse (D7): room_id, as_of, and occupants with all
    pre-U2 CurrentLocationOut fields are present; new fields room_name and
    per-occupant quality/staleness_seconds/source/display_name are added.
    """
    occupants = await svc.occupants_of(room_id)
    now = datetime.now(UTC)
    room_name = occupants[0].room_name if occupants else ""
    display_names = _display_names_for([o.person_id for o in occupants], db)
    return RoomOccupancyEnvelope(
        room_id=room_id,
        room_name=room_name,
        as_of=now,
        occupants=[
            _loc_to_envelope(o, display_name=display_names.get(o.person_id, ""), now=now)
            for o in occupants
        ],
    )


# ---------------------------------------------------------------------------
# GET /persons/{person_id}/dwell  (unchanged)
# ---------------------------------------------------------------------------


@router.get("/persons/{person_id}/dwell", response_model=dict)
async def get_person_dwell(
    person_id: str,
    _auth: AuthContext = Depends(require_permission("persons.read")),
    svc: PersonLocationService = Depends(_get_service),
) -> dict:
    """Return the currently-open segment for a person."""
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


# ---------------------------------------------------------------------------
# POST /persons/{person_id}/location/override  (unchanged)
# ---------------------------------------------------------------------------


@router.post(
    "/persons/{person_id}/location/override",
    status_code=status.HTTP_201_CREATED,
)
async def override_person_location(
    person_id: str,
    body: LocationOverrideRequest,
    _auth: AuthContext = Depends(require_permission("persons.write_overrides")),
    db: Session = Depends(get_db),
    svc: PersonLocationService = Depends(_get_service),
) -> dict:
    """Manually correct a person's location."""
    await svc.ingest_manual_override(
        person_id=person_id,
        room_id=body.room_id,
        entered_at=body.entered_at,
        note=body.note,
    )
    db.commit()
    return {"status": "ok", "person_id": str(person_id)}
