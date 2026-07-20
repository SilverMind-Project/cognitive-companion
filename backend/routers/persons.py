"""Person tracking API endpoints."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.person import HouseholdMember
from backend.schemas.person import (
    EnrollResultOut,
    HouseholdMemberCreate,
    HouseholdMemberOut,
    HouseholdMemberUpdate,
    PersonEnrollmentOut,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("", response_model=list[HouseholdMemberOut])
async def list_members(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("caregiver")),
):
    """List all household members, enriched with face enrollment status."""
    members = db.query(HouseholdMember).order_by(HouseholdMember.name).all()

    # Fetch enrollment data from the person-id service.
    pid_client = request.app.state.person_id_client
    enrolled_members = await pid_client.get_members()
    enrolled_map = {m.person_id: m for m in enrolled_members}

    results: list[HouseholdMemberOut] = []
    for member in members:
        out = HouseholdMemberOut.model_validate(member)
        enrollment = enrolled_map.get(member.id)
        if enrollment is not None:
            out.is_enrolled = True
            out.embedding_count = enrollment.embedding_count
        results.append(out)

    return results


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

# GET /locations and GET /{person_id}/location live in routers/persons_location.py: they serve
# PersonLocationEnvelope from PersonLocationService (the U2 SSOT, shared with the MCP tools).
# Legacy duplicates here shadowed them at runtime, so do not reintroduce them (C17).


# DEPRECATED: use GET /api/v1/persons/{id}/location instead.
@router.get(
    "/cts/person-location",
    status_code=410,
    deprecated=True,
    include_in_schema=False,
)
async def deprecated_cts_person_location():
    from fastapi.responses import Response as FastAPIResponse

    return FastAPIResponse(
        status_code=410,
        content=(
            "Gone. Use GET /api/v1/persons/{id}/location instead. "
            "See /docs#tag/Persons for the new API surface."
        ),
        headers={"Link": '</api/v1/persons>; rel="successor-version"'},
        media_type="text/plain",
    )


@router.get("/enrolled", response_model=list[PersonEnrollmentOut])
async def list_enrolled(
    request: Request,
    _auth=Depends(require_permission("caregiver")),
):
    """List all people with face enrollment data in the person-id service."""
    pid_client = request.app.state.person_id_client
    enrolled = await pid_client.get_members()
    return [
        PersonEnrollmentOut(
            person_id=m.person_id,
            name=m.name,
            embedding_count=m.embedding_count,
            created_at=m.created_at,
        )
        for m in enrolled
    ]


@router.post("/{person_id}/enroll", response_model=EnrollResultOut)
async def enroll_person(
    person_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("admin")),
):
    """Enroll a person's face by uploading one or more images.

    Accepts multipart file uploads, base64-encodes them, and forwards
    to the person-id service. Also ensures the person exists in the
    local HouseholdMember table.
    """
    pid_client = request.app.state.person_id_client

    # Ensure the person exists locally.
    member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{person_id}' not found")

    # Read and base64-encode uploaded images.
    images: list[str] = []
    for upload in files:
        raw = await upload.read()
        images.append(base64.b64encode(raw).decode("ascii"))

    logger.info(
        "person_enroll_request",
        person_id=person_id,
        image_count=len(images),
    )

    result = await pid_client.enroll(
        person_id=person_id,
        name=member.name,
        images=images,
    )
    if result is None:
        raise HTTPException(
            status_code=502,
            detail="Person identification service is unavailable",
        )

    return EnrollResultOut(
        person_id=result.person_id,
        name=result.name,
        embedding_count=result.embedding_count,
        status=result.status,
    )


@router.get("/{person_id}/enrollment", response_model=PersonEnrollmentOut)
async def get_enrollment(
    person_id: str,
    request: Request,
    _auth=Depends(require_permission("caregiver")),
):
    """Get face enrollment details for a specific person."""
    pid_client = request.app.state.person_id_client
    info = await pid_client.get_member(person_id)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"No enrollment found for '{person_id}'",
        )
    return PersonEnrollmentOut(
        person_id=info.person_id,
        name=info.name,
        embedding_count=info.embedding_count,
        created_at=info.created_at,
    )


@router.delete("/{person_id}/enrollment", status_code=204)
async def delete_enrollment(
    person_id: str,
    request: Request,
    _auth=Depends(require_permission("admin")),
):
    """Remove face enrollment data for a person."""
    pid_client = request.app.state.person_id_client
    deleted = await pid_client.delete_member(person_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No enrollment found for '{person_id}'",
        )
    logger.info("person_enrollment_deleted", person_id=person_id)


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


