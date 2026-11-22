"""Person tracking API endpoints."""

from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, actor_from_auth, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError
from backend.integrations.minio_client import MinioClient
from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.models.cts_signal import DementiaSignal
from backend.models.person import HouseholdMember
from backend.routers.dependencies import (
    get_config_minio_client,
    get_face_calibration_service,
    get_roster_health_service,
)
from backend.schemas.identity_roster import RosterHealthEnvelope
from backend.schemas.person import (
    EnrollResultOut,
    HouseholdMemberCreate,
    HouseholdMemberOut,
    HouseholdMemberUpdate,
    PersonEnrollmentOut,
    PersonHeightProfileOut,
    PersonHeightSyncItem,
    PersonPrototypesResponse,
    RebuildPrototypesResponse,
)
from backend.services.face_calibration import FaceCalibrationReviewService
from backend.services.identity_roster import RosterHealthService
from backend.services.persons import insert_household_member
from backend.services.wearables.binding_service import WearableBindingService

logger = get_logger(__name__)

router = APIRouter(prefix="/persons", tags=["persons"])

_PROTOTYPE_PRESIGN_TTL = 3600


def _presigner(minio: MinioClient):
    def presign(key: str | None) -> str | None:
        if not key:
            return None
        return minio.generate_presigned_url(key, expiration=_PROTOTYPE_PRESIGN_TTL)

    return presign


def _pid_upstream(exc: PersonIDUpstreamError) -> HTTPException:
    return HTTPException(status_code=502 if exc.status >= 500 else exc.status, detail=exc.message)


@router.get("", response_model=list[HouseholdMemberOut])
async def list_members(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("persons:read")),
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
    _auth=Depends(require_permission("persons:write")),
):
    """Register a new household member."""
    existing = db.query(HouseholdMember).filter(HouseholdMember.id == body.id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Member '{body.id}' already exists")

    return insert_household_member(
        db,
        id=body.id,
        name=body.name,
        is_guest=body.is_guest,
        height_cm=body.height_cm,
        metadata_json=body.metadata_json,
    )


# Static paths must be defined before /{person_id} to avoid being
# captured by the path parameter.

# GET /locations and GET /{person_id}/location live in routers/persons_location.py: they serve
# PersonLocationEnvelope from PersonLocationService (the U2 SSOT, shared with the MCP tools).
# Legacy duplicates here shadowed them at runtime, so do not reintroduce them.


@router.get("/enrolled", response_model=list[PersonEnrollmentOut])
async def list_enrolled(
    request: Request,
    _auth=Depends(require_permission("persons:read")),
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


@router.get("/heights", response_model=list[PersonHeightSyncItem])
async def list_member_heights(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("persons.heights:read")),
) -> list[PersonHeightSyncItem]:
    """Minimal member height roster for CTS operator-height sync (reads local DB only)."""
    members = db.query(HouseholdMember).order_by(HouseholdMember.id).all()
    return [
        PersonHeightSyncItem(person_id=member.id, height_cm=member.height_cm) for member in members
    ]


@router.get("/roster-health", response_model=RosterHealthEnvelope)
async def get_roster_health(
    svc: RosterHealthService = Depends(get_roster_health_service),
    _auth=Depends(require_permission("persons:read")),
) -> RosterHealthEnvelope:
    """Members still needing face enrollment and recurring visitors awaiting review."""
    try:
        return await svc.get_roster_health()
    except PersonIDUpstreamError as exc:
        status = 502 if exc.status >= 500 else exc.status
        raise HTTPException(status_code=status, detail=exc.message) from exc


@router.post("/{person_id}/enroll", response_model=EnrollResultOut)
async def enroll_person(
    person_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("persons.enrollment:write")),
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

    orch_client = request.app.state.__dict__.get("orchestrator_client")
    if orch_client is not None:
        try:
            await orch_client.sync_gallery_identities()
        except UpstreamError, OSError:
            logger.warning("cts_roster_sync_on_enroll_failed", person_id=person_id)

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
    _auth=Depends(require_permission("persons:read")),
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
    _auth=Depends(require_permission("persons.enrollment:delete")),
):
    """Remove face enrollment data for a person."""
    pid_client = request.app.state.person_id_client
    deleted = await pid_client.delete_member(person_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No enrollment found for '{person_id}'",
        )
    orch_client = request.app.state.__dict__.get("orchestrator_client")
    if orch_client is not None:
        try:
            await orch_client.purge_gallery_identity(person_id)
        except UpstreamError, OSError:
            logger.warning("cts_identity_purge_on_unenroll_failed", person_id=person_id)
    logger.info("person_enrollment_deleted", person_id=person_id)


@router.get("/{person_id}/prototypes", response_model=PersonPrototypesResponse)
async def list_person_prototypes(
    person_id: str,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("face_prototypes:read")),
) -> PersonPrototypesResponse:
    """List pose-binned face prototypes for one enrolled member."""
    try:
        return await svc.list_prototypes(person_id, presign=_presigner(minio))
    except PersonIDUpstreamError as exc:
        raise _pid_upstream(exc) from exc


@router.post("/{person_id}/prototypes/rebuild", response_model=RebuildPrototypesResponse)
async def rebuild_person_prototypes(
    person_id: str,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    auth: AuthContext = Depends(require_permission("face_prototypes:write")),
) -> RebuildPrototypesResponse:
    """Rebuild pose-binned face prototypes for one enrolled member."""
    actor = actor_from_auth(auth)
    try:
        result = await svc.rebuild_prototypes(person_id)
    except PersonIDUpstreamError as exc:
        raise _pid_upstream(exc) from exc
    logger.info(
        "person_prototypes_rebuilt",
        person_id=person_id,
        prototype_count=result.prototype_count,
        actor=actor,
    )
    return result


@router.delete("/{person_id}/prototypes/{prototype_id}", status_code=204)
async def delete_person_prototype(
    person_id: str,
    prototype_id: str,
    svc: FaceCalibrationReviewService = Depends(get_face_calibration_service),
    auth: AuthContext = Depends(require_permission("face_prototypes:write")),
) -> Response:
    """Remove a face prototype and its underlying embedding(s), rebuilding the gallery."""
    actor = actor_from_auth(auth)
    try:
        await svc.delete_prototype(person_id, prototype_id)
    except PersonIDUpstreamError as exc:
        raise _pid_upstream(exc) from exc
    logger.info(
        "person_prototype_deleted",
        person_id=person_id,
        prototype_id=prototype_id,
        actor=actor,
    )
    return Response(status_code=204)


@router.get("/{person_id}/height-profile", response_model=PersonHeightProfileOut)
async def get_person_height_profile(
    person_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("persons:read")),
) -> PersonHeightProfileOut:
    """Return the operator-entered height and effective CTS standing height profile."""
    member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{person_id}' not found")

    orch_client = getattr(request.app.state, "orchestrator_client", None)
    if orch_client is None:
        return PersonHeightProfileOut(
            person_id=person_id,
            operator_height_cm=member.height_cm,
            cts_available=False,
        )

    try:
        profile = await orch_client.get_identity_height_profile(person_id)
    except UpstreamError, OSError:
        logger.warning("cts_height_profile_fetch_failed", person_id=person_id)
        return PersonHeightProfileOut(
            person_id=person_id,
            operator_height_cm=member.height_cm,
            cts_available=False,
        )

    if profile is None:
        return PersonHeightProfileOut(
            person_id=person_id,
            operator_height_cm=member.height_cm,
            cts_available=True,
        )

    return PersonHeightProfileOut(
        person_id=person_id,
        operator_height_cm=member.height_cm,
        effective_height_m=profile.get("height_m"),
        effective_sigma_m=profile.get("height_sigma_m"),
        source=profile.get("source"),
        samples=int(profile.get("samples", 0)),
        cameras=int(profile.get("cameras", 0)),
        updated_at=profile.get("updated_at"),
        cts_available=True,
    )


@router.get("/{person_id}", response_model=HouseholdMemberOut)
async def get_member(
    person_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("persons:read")),
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
    _auth=Depends(require_permission("persons:write")),
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
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_permission("persons:delete")),
):
    """Remove a household member and purge associated enrollment/tracking anchors."""
    member = db.query(HouseholdMember).filter(HouseholdMember.id == person_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{person_id}' not found")
    db.query(DementiaSignal).filter(DementiaSignal.person_id == person_id).delete()
    WearableBindingService.close_active_bindings_for_member(db, person_id)
    db.delete(member)
    db.commit()

    pid_client = request.app.state.__dict__.get("person_id_client")
    if pid_client is not None:
        await pid_client.delete_member(person_id)

    orch_client = request.app.state.__dict__.get("orchestrator_client")
    if orch_client is not None:
        try:
            await orch_client.purge_gallery_identity(person_id)
        except UpstreamError, OSError:
            logger.warning("cts_identity_purge_on_member_remove_failed", person_id=person_id)
