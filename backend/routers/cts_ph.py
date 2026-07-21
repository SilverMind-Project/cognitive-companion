"""CC BFF gateway for Person Hypotheses.

Proxies orchestrator /ph/* endpoints, enriches responses with presigned
image URLs and posterior top-label data.  Requires ``cts.identity.view``
for reads and ``cts.identity.correct`` for mutations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled, presigned_image_url
from backend.routers.dependencies import (
    get_identity_correction_service,
    get_orchestrator_client,
    get_ph_enrichment_service,
)
from backend.schemas.cts_correction import (
    ApplySegmentRequest,
    CorrectionJobResponse,
    CorrectionResultResponse,
    ProposeSegmentRequest,
    SegmentProposalResponse,
)
from backend.schemas.cts_ph import (
    BatchCorrectRequest,
    BatchCorrectResponse,
    BatchDeleteRequest,
    BatchDeleteResponse,
    BatchMergeRequest,
    BatchMergeResponse,
    CorrectIdentityRequest,
    CorrectIdentityResponse,
    CorrectionTargetResponse,
    CorrectionTargetsResponse,
    MergeRequest,
    MergeResponse,
    PaginatedPHList,
    PHCoPresentResponse,
    PHDetailResponse,
    PHKeyframesResponse,
    PHObservationsResponse,
    PHSummaryResponse,
    PHTrailResponse,
    PurgeUnknownRequest,
    PurgeUnknownResponse,
    RevisionsFeedResponse,
    SplitRequest,
    SplitResponse,
)
from backend.services.cts.correction_targets import list_correction_targets
from backend.services.cts.identity_correction_service import (
    CorrectionContractError,
    CorrectionUpstreamError,
    IdentityCorrectionService,
)
from backend.services.cts.ph_enrichment import PHEnrichmentService

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-ph"])


async def _upstream_or_502[T](call: Awaitable[T], *, endpoint: str) -> T:
    try:
        return await call
    except UpstreamError as exc:
        logger.warning(
            "cts_ph_upstream_failed",
            endpoint=endpoint,
            service=exc.service,
            upstream_status=exc.status,
        )
        raise HTTPException(
            status_code=502 if exc.status >= 500 else exc.status,
            detail={
                "code": str(exc.code),
                "message": f"{exc.service} returned HTTP {exc.status}",
                "service": exc.service,
            },
        ) from exc


def _required_mapping_list(
    data: Mapping[str, Any], key: str, *, endpoint: str
) -> list[dict[str, Any]]:
    if key not in data:
        logger.error("cts_ph_upstream_contract_missing_field", endpoint=endpoint, field=key)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "cts_ph.upstream_contract",
                "message": f"tracking_orchestrator response missing required field {key}",
                "service": "tracking_orchestrator",
            },
        )
    value = data[key]
    if not isinstance(value, list):
        logger.error(
            "cts_ph_upstream_contract_invalid_field",
            endpoint=endpoint,
            field=key,
            field_type=type(value).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "cts_ph.upstream_contract",
                "message": f"tracking_orchestrator field {key} must be a list",
                "service": "tracking_orchestrator",
            },
        )
    items: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            logger.error(
                "cts_ph_upstream_contract_invalid_item",
                endpoint=endpoint,
                field=key,
                index=index,
                item_type=type(item).__name__,
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "cts_ph.upstream_contract",
                    "message": f"tracking_orchestrator field {key}[{index}] must be an object",
                    "service": "tracking_orchestrator",
                },
            )
        items.append(dict(item))
    return items


def _required_value(data: Mapping[str, Any], key: str, *, endpoint: str) -> Any:
    if key in data:
        return data[key]
    logger.error("cts_ph_upstream_contract_missing_field", endpoint=endpoint, field=key)
    raise HTTPException(
        status_code=502,
        detail={
            "code": "cts_ph.upstream_contract",
            "message": f"tracking_orchestrator response missing required field {key}",
            "service": "tracking_orchestrator",
        },
    )


# ---------------------------------------------------------------------------
# Read endpoints (cts.identity.view)
# ---------------------------------------------------------------------------


@router.get("/identity/correction-targets", response_model=CorrectionTargetsResponse)
async def get_correction_targets(
    db: Session = Depends(get_db),
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.view")),
) -> CorrectionTargetsResponse:
    """Authoritative correction-target list: active household members.

    Independent of ReID gallery population; gallery counts are decoration only,
    and an upstream gallery failure is surfaced via ``gallery_available`` rather
    than dropping targets.
    """
    cts_enabled()
    result = await list_correction_targets(db, client)
    return CorrectionTargetsResponse(
        targets=[
            CorrectionTargetResponse(
                identity_id=t.identity_id,
                display_name=t.display_name,
                is_active=t.is_active,
                is_guest=t.is_guest,
                gallery_entry_count=t.gallery_entry_count,
                gallery_verified_count=t.gallery_verified_count,
            )
            for t in result.targets
        ],
        gallery_available=result.gallery_available,
        gallery_error=result.gallery_error,
    )


@router.get("/ph", response_model=PaginatedPHList)
async def list_phs(
    request: Request,
    since: str | None = None,
    until: str | None = None,
    room_id: str | None = None,
    identity_id: str | None = None,
    state: str | None = None,
    include_transient: bool = False,
    min_duration_s: float | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    enricher: PHEnrichmentService = Depends(get_ph_enrichment_service),
    _auth=Depends(require_permission("cts.identity.view")),
) -> PaginatedPHList:
    cts_enabled()
    data = await client.list_phs(
        since=since,
        until=until,
        room_id=room_id,
        identity_id=identity_id,
        state=state,
        include_transient=include_transient,
        min_duration_s=min_duration_s,
        search=search,
        limit=limit,
        offset=offset,
    )
    enriched = await enricher.enrich_phs(
        _required_mapping_list(data, "items", endpoint="list_phs"),
        image_url=lambda key: presigned_image_url(request, key),
    )
    items = [PHSummaryResponse(**item) for item in enriched]
    return PaginatedPHList(
        items=items,
        total=_required_value(data, "total", endpoint="list_phs"),
        limit=_required_value(data, "limit", endpoint="list_phs"),
        offset=_required_value(data, "offset", endpoint="list_phs"),
    )


@router.get("/ph/revisions", response_model=RevisionsFeedResponse)
async def list_revisions(
    ph_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    before_id: str | None = None,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.view")),
) -> RevisionsFeedResponse:
    cts_enabled()
    data = await client.list_ph_revisions(ph_id=ph_id, kind=kind, limit=limit, before_id=before_id)
    return RevisionsFeedResponse(**data)


@router.get("/ph/{ph_id}", response_model=PHDetailResponse)
async def get_ph(
    ph_id: str,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    enricher: PHEnrichmentService = Depends(get_ph_enrichment_service),
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHDetailResponse:
    cts_enabled()
    data = await _upstream_or_502(client.get_ph(ph_id), endpoint="get_ph")
    data = await enricher.enrich_ph(data, image_url=lambda key: presigned_image_url(request, key))
    return PHDetailResponse(**data)


@router.get("/ph/{ph_id}/observations", response_model=PHObservationsResponse)
async def list_ph_observations(
    ph_id: str,
    limit: int = 200,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHObservationsResponse:
    cts_enabled()
    data = await client.list_ph_observations(ph_id, limit=limit)
    return PHObservationsResponse(**data)


@router.get("/ph/{ph_id}/keyframes", response_model=PHKeyframesResponse)
async def list_ph_keyframes(
    request: Request,
    ph_id: str,
    limit: int = 24,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    enricher: PHEnrichmentService = Depends(get_ph_enrichment_service),
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHKeyframesResponse:
    cts_enabled()
    data = await client.list_ph_keyframes(ph_id, limit=limit)
    data["items"] = enricher.enrich_keyframes(
        _required_mapping_list(data, "items", endpoint="list_ph_keyframes"),
        image_url=lambda key: presigned_image_url(request, key),
    )
    return PHKeyframesResponse(**data)


@router.get("/ph/{ph_id}/trail", response_model=PHTrailResponse)
async def get_ph_trail(
    ph_id: str,
    since: str | None = None,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHTrailResponse:
    cts_enabled()
    data = await client.get_ph_trail(ph_id, since=since)
    return PHTrailResponse(**data)


@router.get("/ph/{ph_id}/co_present", response_model=PHCoPresentResponse)
async def get_co_present(
    ph_id: str,
    radius_m: float = 5.0,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    enricher: PHEnrichmentService = Depends(get_ph_enrichment_service),
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHCoPresentResponse:
    cts_enabled()
    data = await _upstream_or_502(
        client.get_ph_co_present(ph_id, radius_m=radius_m),
        endpoint="get_co_present",
    )
    display_names = await enricher.identity_display_names()
    data["co_present"] = enricher.enrich_co_present(
        _required_mapping_list(data, "co_present", endpoint="get_co_present"),
        display_names=display_names,
    )
    return PHCoPresentResponse(**data)


# ---------------------------------------------------------------------------
# Mutation endpoints (cts.identity.correct)
# ---------------------------------------------------------------------------


def _actor(request: Request) -> str:
    auth = getattr(request.state, "auth_context", None)
    return getattr(auth, "subject", "system") if auth else "system"


@router.post("/ph/{ph_id}/correct", response_model=CorrectIdentityResponse)
async def correct_identity(
    ph_id: str,
    body: CorrectIdentityRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> CorrectIdentityResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    data = await client.correct_ph_identity(
        ph_id=ph_id,
        new_identity_id=body.new_identity_id,
        reason=body.reason,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return CorrectIdentityResponse(**data)


@router.post("/ph/merge", response_model=MergeResponse)
async def merge_phs(
    body: MergeRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> MergeResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    data = await client.merge_phs(
        source_ph_id=body.source_ph_id,
        target_ph_id=body.target_ph_id,
        reason=body.reason,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return MergeResponse(**data)


@router.post("/ph/batch_merge", response_model=BatchMergeResponse)
async def batch_merge_phs(
    body: BatchMergeRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> BatchMergeResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    data = await client.batch_merge_phs(
        source_ph_ids=body.source_ph_ids,
        target_ph_id=body.target_ph_id,
        reason=body.reason,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return BatchMergeResponse(**data)


@router.post("/ph/{ph_id}/split", response_model=SplitResponse)
async def split_ph(
    ph_id: str,
    body: SplitRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> SplitResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    data = await client.split_ph(
        ph_id=ph_id,
        at_observation_id=body.at_observation_id,
        reason=body.reason,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return SplitResponse(**data)


@router.post("/ph/batch_correct", response_model=BatchCorrectResponse)
async def batch_correct(
    body: BatchCorrectRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> BatchCorrectResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    corrections = [item.model_dump() for item in body.corrections]
    data = await client.batch_correct_phs(
        corrections=corrections,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return BatchCorrectResponse(**data)


@router.post("/ph/batch_delete", response_model=BatchDeleteResponse)
async def batch_delete(
    body: BatchDeleteRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> BatchDeleteResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    data = await client.batch_delete_phs(
        ph_ids=body.ph_ids,
        reason=body.reason,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return BatchDeleteResponse(**data)


@router.post("/ph/purge_unknown", response_model=PurgeUnknownResponse)
async def purge_unknown(
    body: PurgeUnknownRequest,
    request: Request,
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> PurgeUnknownResponse:
    cts_enabled()
    idempotency_key = request.headers.get("X-Idempotency-Key")
    data = await client.purge_unknown_phs(
        older_than_days=body.older_than_days,
        limit=body.limit,
        actor=_actor(request),
        idempotency_key=idempotency_key,
    )
    return PurgeUnknownResponse(**data)


# ---------------------------------------------------------------------------
# Segment correction workflow: propose / apply / compensate / job status
# ---------------------------------------------------------------------------


def _raise_for_correction(exc: CorrectionUpstreamError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={
            "code": exc.code,
            "message": exc.message,
            "service": "tracking_orchestrator",
        },
    )


@router.post("/identity/corrections/propose", response_model=SegmentProposalResponse)
async def propose_correction_segment(
    body: ProposeSegmentRequest,
    svc: IdentityCorrectionService = Depends(get_identity_correction_service),
    _auth=Depends(require_permission("cts.identity.view")),
) -> SegmentProposalResponse:
    """Advisory observation-bounded segment proposal for caregiver review."""
    cts_enabled()
    try:
        return await svc.propose_segment(
            ph_id=body.ph_id, observation_id=body.observation_id, at=body.at
        )
    except CorrectionUpstreamError as exc:
        raise _raise_for_correction(exc) from exc
    except CorrectionContractError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "correction.upstream_contract", "message": str(exc)},
        ) from exc


@router.post("/identity/corrections/apply", response_model=CorrectionResultResponse)
async def apply_correction_segment(
    body: ApplySegmentRequest,
    request: Request,
    svc: IdentityCorrectionService = Depends(get_identity_correction_service),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> CorrectionResultResponse:
    """Apply an explicit frame-only/bounded correction or Set-to-Unknown.

    The audited actor is taken from the auth context, never from the browser.
    A stale ``base_ph_version`` returns 409 ``correction.stale_version``.
    """
    cts_enabled()
    try:
        return await svc.apply_correction(
            payload=body.model_dump(exclude_none=True), actor=_actor(request)
        )
    except CorrectionUpstreamError as exc:
        raise _raise_for_correction(exc) from exc
    except CorrectionContractError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "correction.upstream_contract", "message": str(exc)},
        ) from exc


@router.post(
    "/identity/corrections/{correction_id}/compensate",
    response_model=CorrectionResultResponse,
)
async def compensate_correction(
    correction_id: str,
    request: Request,
    svc: IdentityCorrectionService = Depends(get_identity_correction_service),
    _auth=Depends(require_permission("cts.identity.correct")),
) -> CorrectionResultResponse:
    """Undo a correction via a compensating revision (never deletes the original)."""
    cts_enabled()
    try:
        return await svc.compensate(correction_id=correction_id, actor=_actor(request))
    except CorrectionUpstreamError as exc:
        raise _raise_for_correction(exc) from exc
    except CorrectionContractError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "correction.upstream_contract", "message": str(exc)},
        ) from exc


@router.get("/identity/corrections/jobs/{revision_id}", response_model=CorrectionJobResponse)
async def get_correction_job(
    revision_id: str,
    svc: IdentityCorrectionService = Depends(get_identity_correction_service),
    _auth=Depends(require_permission("cts.identity.view")),
) -> CorrectionJobResponse:
    """Projection-job status for a revision; polled until terminal."""
    cts_enabled()
    try:
        return await svc.get_job(revision_id=revision_id)
    except CorrectionUpstreamError as exc:
        raise _raise_for_correction(exc) from exc
    except CorrectionContractError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "correction.upstream_contract", "message": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# Identity gallery (needed by admin UI for correction forms)
# ---------------------------------------------------------------------------


@router.get("/identity/identities")
async def list_identities(
    client: OrchestratorClient = Depends(get_orchestrator_client),
    _auth=Depends(require_permission("cts.identity.view")),
) -> dict:
    cts_enabled()
    identities = await client.get_identities()
    return {"identities": identities}
