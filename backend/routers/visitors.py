"""Visitor cluster admin routes (browser-facing BFF).

Every route is gated by ``require_token("visitors.review")``, a strict token
check that ignores the broad ``GET /api/v1/*`` role glob (the same pattern
`cts_reid_review.py` uses for gallery review): a caller holding only
``caregiver`` is rejected.

Unlike the CTS admin routers, this surface does not call ``cts_enabled()``.
Visitor review depends on ``person_id_client`` (person-identification-service),
which runs independently of ``cts.enabled``; gating it on CTS would hide
visitor naming whenever tracking is disabled or down, even though naming a
visitor has nothing to do with camera tracking.

The routes are thin: all upstream calls, envelope mapping, presigning, and the
two-system naming transaction live in :class:`VisitorAdminService`. The
audited actor is taken from the auth context, never the browser (request
bodies use ``extra="forbid"`` and carry no actor field).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, actor_from_auth, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.routers.dependencies import (
    get_config_minio_client,
    get_identity_review_registry,
    get_visitor_admin_service,
)
from backend.schemas.identity_review import BatchReviewResponse, VisitorReviewRequest
from backend.schemas.visitors import (
    NameVisitorRequest,
    NameVisitorResponse,
    VisitorClusterDetailView,
    VisitorClusterListResponse,
    VisitorClusterView,
)
from backend.services.identity_review.registry import IdentityReviewRegistry, ReviewSubject
from backend.services.visitors import (
    PersonIDUpstreamError,
    VisitorAdminService,
    VisitorPartialFailureError,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/visitors", tags=["visitors"])

_VISITORS_REVIEW = "visitors:review"
_PRESIGN_TTL = 3600  # 1 hour; sized for a caregiver review session


def _presigner(minio: MinioClient):
    def presign(key: str | None) -> str | None:
        if not key:
            return None
        return minio.generate_presigned_url(key, expiration=_PRESIGN_TTL)

    return presign


def _raise_for_upstream(exc: PersonIDUpstreamError) -> HTTPException:
    status = 502 if exc.status >= 500 else exc.status
    return HTTPException(status_code=status, detail=exc.message)


@router.get("/clusters", response_model=VisitorClusterListResponse)
async def list_clusters(
    status: str | None = None,
    svc: VisitorAdminService = Depends(get_visitor_admin_service),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth=Depends(require_permission(_VISITORS_REVIEW)),
) -> VisitorClusterListResponse:
    try:
        return await svc.list_clusters(status=status, presign=_presigner(minio))
    except PersonIDUpstreamError as exc:
        raise _raise_for_upstream(exc) from exc


@router.get("/clusters/{cluster_id}", response_model=VisitorClusterDetailView)
async def get_cluster(
    cluster_id: str,
    svc: VisitorAdminService = Depends(get_visitor_admin_service),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth=Depends(require_permission(_VISITORS_REVIEW)),
) -> VisitorClusterDetailView:
    try:
        return await svc.get_cluster(cluster_id, presign=_presigner(minio))
    except PersonIDUpstreamError as exc:
        raise _raise_for_upstream(exc) from exc


@router.post("/clusters/{cluster_id}/name", response_model=NameVisitorResponse)
async def name_cluster(
    cluster_id: str,
    body: NameVisitorRequest,
    db: Session = Depends(get_db),
    svc: VisitorAdminService = Depends(get_visitor_admin_service),
    auth: AuthContext = Depends(require_permission(_VISITORS_REVIEW)),
) -> NameVisitorResponse:
    try:
        result = await svc.name_cluster(cluster_id, person_id=body.person_id, name=body.name, db=db)
    except PersonIDUpstreamError as exc:
        raise _raise_for_upstream(exc) from exc
    except VisitorPartialFailureError as exc:
        logger.error(
            "visitor_naming_partial_failure",
            cluster_id=cluster_id,
            person_id=exc.person_id,
            actor=actor_from_auth(auth),
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "visitors.partial_failure",
                "message": str(exc),
                "person_id": exc.person_id,
            },
        ) from exc

    logger.info(
        "visitor_cluster_named",
        cluster_id=cluster_id,
        person_id=result.named_person_id,
        actor=actor_from_auth(auth),
    )
    return result


@router.post("/clusters/review", response_model=BatchReviewResponse)
async def review_clusters(
    body: VisitorReviewRequest,
    registry: IdentityReviewRegistry = Depends(get_identity_review_registry),
    auth: AuthContext = Depends(require_permission(_VISITORS_REVIEW)),
) -> BatchReviewResponse:
    """Say who several clusters are: an existing member (attribute) or nobody (dismiss).

    Never enrolls anything. One result per cluster; a missing or named cluster fails alone.
    """
    actor = actor_from_auth(auth)
    try:
        result = await registry.decide(
            "visitors",
            body.verdict,
            [ReviewSubject(id=cluster_id) for cluster_id in body.cluster_ids],
            actor=actor,
            target_identity_id=body.target_identity_id,
        )
    except PersonIDUpstreamError as exc:
        raise _raise_for_upstream(exc) from exc

    logger.info(
        "visitor_clusters_reviewed",
        verdict=body.verdict,
        reviewed=result.reviewed,
        failed=result.failed,
        actor=actor,
    )
    return result


@router.post("/clusters/{cluster_a}/merge/{cluster_b}", response_model=VisitorClusterView)
async def merge_clusters(
    cluster_a: str,
    cluster_b: str,
    svc: VisitorAdminService = Depends(get_visitor_admin_service),
    minio: MinioClient = Depends(get_config_minio_client),
    auth: AuthContext = Depends(require_permission(_VISITORS_REVIEW)),
) -> VisitorClusterView:
    try:
        result = await svc.merge_clusters(cluster_a, cluster_b, presign=_presigner(minio))
    except PersonIDUpstreamError as exc:
        raise _raise_for_upstream(exc) from exc

    logger.info(
        "visitor_clusters_merged",
        cluster_a=cluster_a,
        cluster_b=cluster_b,
        actor=actor_from_auth(auth),
    )
    return result
