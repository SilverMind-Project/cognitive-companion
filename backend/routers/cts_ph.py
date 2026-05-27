"""N2: CC BFF gateway for Person Hypotheses.

Proxies orchestrator /ph/* endpoints, enriches responses with display names,
colours, room names, and presigned image URLs.  Requires ``cts.identity.view``
for reads and ``cts.identity.correct`` for mutations.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from backend.core.logging import get_logger

from backend.core.auth import require_permission
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled, presigned_image_url
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

logger = get_logger(__name__)

router = APIRouter(tags=["cts-ph"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enrich(obj: dict, request: Request) -> dict:
    """Add identity display name, colour, room name, and presigned image URL."""
    identity_id = obj.get("current_identity_id")
    if identity_id:
        registry = getattr(request.app.state, "identity_registry", None)
        if registry is not None:
            obj["identity_display_name"] = registry.get_display_name(identity_id)
            obj["identity_color"] = registry.get_color(identity_id)
    room_id = obj.get("room_id")
    if room_id:
        room_registry = getattr(request.app.state, "room_registry", None)
        if room_registry is not None:
            room = room_registry.get(room_id)
            if room is not None:
                obj["room_name"] = getattr(room, "name", None)
    minio_key = obj.get("latest_keyframe_minio_key")
    if minio_key:
        obj["latest_keyframe_image_url"] = presigned_image_url(request, minio_key)
    return obj


def _get_client(request: Request) -> OrchestratorClient:
    client = getattr(request.app.state, "orchestrator_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail={"code": "cts.upstream_unavailable"})
    return client


# ---------------------------------------------------------------------------
# Read endpoints (cts.identity.view)
# ---------------------------------------------------------------------------


@router.get("/ph", response_model=PaginatedPHList)
async def list_phs(
    request: Request,
    since: str | None = None,
    room_id: str | None = None,
    identity_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _auth=Depends(require_permission("cts.identity.view")),
) -> PaginatedPHList:
    cts_enabled()
    client = _get_client(request)
    data = await client.list_phs(
        since=since, room_id=room_id, identity_id=identity_id, limit=limit, offset=offset,
    )
    items = []
    for item in data.get("items", []):
        _enrich(item, request)
        items.append(PHSummaryResponse(**item))
    return PaginatedPHList(
        items=items,
        total=data.get("total", 0),
        limit=data.get("limit", limit),
        offset=data.get("offset", offset),
    )


@router.get("/ph/revisions", response_model=RevisionsFeedResponse)
async def list_revisions(
    request: Request,
    ph_id: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    before_id: str | None = None,
    _auth=Depends(require_permission("cts.identity.view")),
) -> RevisionsFeedResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.list_ph_revisions(ph_id=ph_id, kind=kind, limit=limit, before_id=before_id)
    return RevisionsFeedResponse(**data)


@router.get("/ph/{ph_id}", response_model=PHDetailResponse)
async def get_ph(
    ph_id: str,
    request: Request,
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHDetailResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.get_ph(ph_id)
    _enrich(data, request)
    return PHDetailResponse(**data)


@router.get("/ph/{ph_id}/observations", response_model=PHObservationsResponse)
async def list_ph_observations(
    ph_id: str,
    request: Request,
    limit: int = 200,
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHObservationsResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.list_ph_observations(ph_id, limit=limit)
    return PHObservationsResponse(**data)


@router.get("/ph/{ph_id}/keyframes", response_model=PHKeyframesResponse)
async def list_ph_keyframes(
    ph_id: str,
    request: Request,
    limit: int = 24,
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHKeyframesResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.list_ph_keyframes(ph_id, limit=limit)
    return PHKeyframesResponse(**data)


@router.get("/ph/{ph_id}/trail", response_model=PHTrailResponse)
async def get_ph_trail(
    ph_id: str,
    request: Request,
    since: str | None = None,
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHTrailResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.get_ph_trail(ph_id, since=since)
    return PHTrailResponse(**data)


@router.get("/ph/{ph_id}/co_present", response_model=PHCoPresentResponse)
async def get_co_present(
    ph_id: str,
    request: Request,
    radius_m: float = 5.0,
    _auth=Depends(require_permission("cts.identity.view")),
) -> PHCoPresentResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.get_ph_co_present(ph_id, radius_m=radius_m)
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
    _auth=Depends(require_permission("cts.identity.correct")),
) -> CorrectIdentityResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.correct_ph_identity(
        ph_id=ph_id,
        new_identity_id=body.new_identity_id,
        reason=body.reason,
        actor=_actor(request),
    )
    return CorrectIdentityResponse(**data)


@router.post("/ph/merge", response_model=MergeResponse)
async def merge_phs(
    body: MergeRequest,
    request: Request,
    _auth=Depends(require_permission("cts.identity.correct")),
) -> MergeResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.merge_phs(
        source_ph_id=body.source_ph_id,
        target_ph_id=body.target_ph_id,
        reason=body.reason,
        actor=_actor(request),
    )
    return MergeResponse(**data)


@router.post("/ph/{ph_id}/split", response_model=SplitResponse)
async def split_ph(
    ph_id: str,
    body: SplitRequest,
    request: Request,
    _auth=Depends(require_permission("cts.identity.correct")),
) -> SplitResponse:
    cts_enabled()
    client = _get_client(request)
    data = await client.split_ph(
        ph_id=ph_id,
        at_observation_id=body.at_observation_id,
        reason=body.reason,
        actor=_actor(request),
    )
    return SplitResponse(**data)


@router.post("/ph/batch_correct", response_model=BatchCorrectResponse)
async def batch_correct(
    body: BatchCorrectRequest,
    request: Request,
    _auth=Depends(require_permission("cts.identity.correct")),
) -> BatchCorrectResponse:
    cts_enabled()
    client = _get_client(request)
    corrections = [item.model_dump() for item in body.corrections]
    data = await client.batch_correct_phs(corrections=corrections, actor=_actor(request))
    return BatchCorrectResponse(**data)
