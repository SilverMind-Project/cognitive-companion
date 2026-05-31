"""N2: CC BFF gateway for Person Hypotheses.

Proxies orchestrator /ph/* endpoints, enriches responses with presigned
image URLs and posterior top-label data.  Requires ``cts.identity.view``
for reads and ``cts.identity.correct`` for mutations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.auth import require_permission
from backend.core.logging import get_logger
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled, presigned_image_url
from backend.routers.dependencies import get_orchestrator_client, get_ph_enrichment_service
from backend.schemas.cts_ph import (
    BatchCorrectRequest,
    BatchCorrectResponse,
    CorrectIdentityRequest,
    CorrectIdentityResponse,
    MergeRequest,
    MergeResponse,
    PaginatedPHList,
    PHCoPresentResponse,
    PHDetailResponse,
    PHKeyframesResponse,
    PHObservationsResponse,
    PHSummaryResponse,
    PHTrailResponse,
    RevisionsFeedResponse,
    SplitRequest,
    SplitResponse,
)
from backend.services.cts.ph_enrichment import PHEnrichmentService

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-ph"])


# ---------------------------------------------------------------------------
# Read endpoints (cts.identity.view)
# ---------------------------------------------------------------------------


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
        data.get("items", []),
        image_url=lambda key: presigned_image_url(request, key),
    )
    items = [PHSummaryResponse(**item) for item in enriched]
    return PaginatedPHList(
        items=items,
        total=data.get("total", 0),
        limit=data.get("limit", limit),
        offset=data.get("offset", offset),
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
    data = await client.get_ph(ph_id)
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
        data.get("items", []),
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
    data = await client.get_ph_co_present(ph_id, radius_m=radius_m)
    display_names = await enricher.identity_display_names()
    data["co_present"] = enricher.enrich_co_present(
        data.get("co_present", []),
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
