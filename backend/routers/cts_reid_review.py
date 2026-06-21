"""M09 ReID review-queue routes (browser-facing BFF surface).

Every route is gated by ``require_token("cts.identity.gallery_review")``, a strict
token check that ignores the broad ``GET /api/v1/*`` and ``POST
/api/v1/cts/identity/*`` role globs. A caller holding only ``cts.identity.view``
or ``cts.identity.correct`` is rejected; gallery review is a separate
biometric-admin grant.

The routes are thin: all query logic, envelope validation, identity mapping, and
state-aware media presigning live in :class:`ReIDReviewService`. The audited
actor is taken from the auth context, never the browser.

MCP parity is intentionally excluded. This is an operational biometric-admin
surface, not caregiver-facing domain data: exposing approve/relabel/reject as
agent tools would let an unattended agent re-identify a household member without
operator review. The exemption is asserted in the router tests and recorded in
the public API reference.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.core.auth import require_token
from backend.routers.cts_deps import cts_enabled, presigned_image_url
from backend.routers.dependencies import get_reid_review_service
from backend.schemas.cts_reid_review import (
    ApproveRequest,
    BatchRejectRequest,
    BatchRejectResponse,
    RejectRequest,
    RelabelRequest,
    ReviewCandidateDetailResponse,
    ReviewCandidateListResponse,
    ReviewCandidateView,
    ReviewCountsResponse,
    ReviewEventsResponse,
)
from backend.services.cts.reid_review_service import (
    ReIDReviewService,
    ReviewContractError,
    ReviewUpstreamError,
)

router = APIRouter(prefix="/cts", tags=["cts-reid-review"])

_GALLERY_REVIEW = "cts.identity.gallery_review"


def _actor(request: Request) -> str:
    auth = getattr(request.state, "auth_context", None)
    return getattr(auth, "subject", "system") if auth else "system"


def _presigner(request: Request):
    def presign(key: str | None) -> str | None:
        return presigned_image_url(request, key)

    return presign


def _raise_for_review(exc: ReviewUpstreamError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


def _contract_502(exc: ReviewContractError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": "reid_review.upstream_contract", "message": str(exc)},
    )


@router.get(
    "/identity/reid-review/candidates", response_model=ReviewCandidateListResponse
)
async def list_candidates(
    request: Request,
    state: str = "pending_review",
    identity_id: str | None = None,
    camera_id: str | None = None,
    model_version: str | None = None,
    source_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCandidateListResponse:
    cts_enabled()
    params: dict[str, str] = {"state": state, "limit": str(limit), "offset": str(offset)}
    if identity_id:
        params["identity_id"] = identity_id
    if camera_id:
        params["camera_id"] = camera_id
    if model_version:
        params["model_version"] = model_version
    if source_type:
        params["source_type"] = source_type
    if since:
        params["since"] = since.isoformat()
    if until:
        params["until"] = until.isoformat()
    try:
        return await svc.list_candidates(params=params, presign=_presigner(request))
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.get("/identity/reid-review/counts", response_model=ReviewCountsResponse)
async def review_counts(
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCountsResponse:
    cts_enabled()
    try:
        return await svc.counts()
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.get(
    "/identity/reid-review/candidates/{candidate_id}",
    response_model=ReviewCandidateDetailResponse,
)
async def get_candidate(
    candidate_id: str,
    request: Request,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCandidateDetailResponse:
    cts_enabled()
    try:
        return await svc.get_detail(candidate_id, presign=_presigner(request))
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.get(
    "/identity/reid-review/candidates/{candidate_id}/events",
    response_model=ReviewEventsResponse,
)
async def list_events(
    candidate_id: str,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewEventsResponse:
    cts_enabled()
    try:
        return await svc.list_events(candidate_id)
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.post(
    "/identity/reid-review/candidates/{candidate_id}/approve",
    response_model=ReviewCandidateView,
)
async def approve_candidate(
    candidate_id: str,
    body: ApproveRequest,
    request: Request,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCandidateView:
    cts_enabled()
    try:
        return await svc.approve(
            candidate_id,
            actor=_actor(request),
            base_audit_version=body.base_audit_version,
            note=body.note,
            presign=_presigner(request),
        )
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.post(
    "/identity/reid-review/candidates/{candidate_id}/relabel",
    response_model=ReviewCandidateView,
)
async def relabel_candidate(
    candidate_id: str,
    body: RelabelRequest,
    request: Request,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCandidateView:
    cts_enabled()
    try:
        return await svc.relabel(
            candidate_id,
            actor=_actor(request),
            base_audit_version=body.base_audit_version,
            target_identity_id=body.target_identity_id,
            note=body.note,
            presign=_presigner(request),
        )
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.post(
    "/identity/reid-review/candidates/{candidate_id}/reject",
    response_model=ReviewCandidateView,
)
async def reject_candidate(
    candidate_id: str,
    body: RejectRequest,
    request: Request,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCandidateView:
    cts_enabled()
    try:
        return await svc.reject(
            candidate_id,
            actor=_actor(request),
            base_audit_version=body.base_audit_version,
            reason=body.reason,
            note=body.note,
            presign=_presigner(request),
        )
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.post(
    "/identity/reid-review/reject-batch", response_model=BatchRejectResponse
)
async def reject_batch(
    body: BatchRejectRequest,
    request: Request,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> BatchRejectResponse:
    cts_enabled()
    try:
        return await svc.reject_batch(
            actor=_actor(request),
            reason=body.reason,
            note=body.note,
            items=[item.model_dump() for item in body.items],
        )
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc


@router.post(
    "/identity/reid-review/candidates/{candidate_id}/compensate",
    response_model=ReviewCandidateView,
)
async def compensate_candidate(
    candidate_id: str,
    request: Request,
    svc: ReIDReviewService = Depends(get_reid_review_service),
    _auth=Depends(require_token(_GALLERY_REVIEW)),
) -> ReviewCandidateView:
    cts_enabled()
    try:
        return await svc.compensate(
            candidate_id, actor=_actor(request), presign=_presigner(request)
        )
    except ReviewUpstreamError as exc:
        raise _raise_for_review(exc) from exc
    except ReviewContractError as exc:
        raise _contract_502(exc) from exc
