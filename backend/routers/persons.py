"""Person tracking API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.models.person import HouseholdMember
from backend.schemas.person import (
    HouseholdMemberCreate,
    HouseholdMemberOut,
    HouseholdMemberUpdate,
    PersonLocationHistoryOut,
    PersonLocationOut,
    PersonSightingOut,
)

router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("", response_model=list[HouseholdMemberOut])
async def list_members(
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """List all household members."""
    members = db.query(HouseholdMember).order_by(HouseholdMember.name).all()
    return members


@router.post("", response_model=HouseholdMemberOut, status_code=201)
async def create_member(
    body: HouseholdMemberCreate,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("admin")),
):
    """Register a new household member."""
    existing = db.query(HouseholdMember).filter(HouseholdMember.id == body.id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Member '{body.id}' already exists")

    member = HouseholdMember(
        id=body.id,
        name=body.name,
        is_guest=body.is_guest,
        metadata_json=body.metadata_json,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


# Static paths must be defined before /{person_id} to avoid being
# captured by the path parameter.


@router.get("/locations", response_model=list[PersonLocationOut])
async def get_all_locations(
    request: Request,
    _auth=Depends(require_permission("caregiver")),
):
    """Get current location of all tracked persons."""
    tracking = request.app.state.person_tracking
    locations = await tracking.get_person_locations()
    return locations


@router.get("/{person_id}", response_model=HouseholdMemberOut)
async def get_member(
    person_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """Get a specific household member."""
    member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{person_id}' not found")
    return member


@router.patch("/{person_id}", response_model=HouseholdMemberOut)
async def update_member(
    person_id: str,
    body: HouseholdMemberUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("admin")),
):
    """Update a household member."""
    member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{person_id}' not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{person_id}", status_code=204)
async def delete_member(
    person_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("admin")),
):
    """Remove a household member."""
    member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{person_id}' not found")
    db.delete(member)
    db.commit()


@router.get("/{person_id}/location", response_model=PersonLocationOut)
async def get_person_location(
    person_id: str,
    request: Request,
    _auth=Depends(require_permission("caregiver")),
):
    """Get current location of a specific person."""
    tracking = request.app.state.person_tracking
    location = await tracking.get_person_location(person_id)
    if not location:
        raise HTTPException(status_code=404, detail=f"No location data for '{person_id}'")
    return location


@router.get("/{person_id}/history", response_model=list[PersonLocationHistoryOut])
async def get_location_history(
    person_id: str,
    request: Request,
    hours: float = Query(default=24.0, ge=0.5, le=168),
    _auth=Depends(require_permission("caregiver")),
):
    """Get location timeline for a person."""
    tracking = request.app.state.person_tracking
    history = await tracking.get_location_history(person_id, hours=hours)
    return history


@router.get("/{person_id}/sightings", response_model=list[PersonSightingOut])
async def get_sightings(
    person_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    _auth=Depends(require_permission("caregiver")),
):
    """Get recent camera/sensor sightings for a person."""
    tracking = request.app.state.person_tracking
    sightings = await tracking.get_recent_sightings(person_id, limit=limit)
    return sightings
