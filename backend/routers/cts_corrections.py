"""CTS identity corrections, merges, batch operations, and tracklet management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.integrations._upstream_base import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled
from backend.routers.cts_identity_helpers import write_manual_revision_log
from backend.routers.dependencies import get_orchestrator_client

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/identity", tags=["cts-corrections"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CorrectionRequest(BaseModel):
    global_track_id: str = Field(default="", min_length=0, max_length=128)
    new_identity_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="manual", max_length=512)
    display_name: str | None = Field(default=None, max_length=128)
    evidence: dict[str, Any] = Field(default_factory=dict)
    annotation_id: str | None = Field(default=None, max_length=128)


class MergeRequest(BaseModel):
    global_track_id: str = Field(..., min_length=1, max_length=128)
    from_identity_id: str = Field(..., min_length=1, max_length=128)
    to_identity_id: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="manual_merge", max_length=512)


class BatchCorrectionItem(BaseModel):
    global_track_id: str = Field(..., min_length=1, max_length=128)
    new_identity_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="manual", max_length=512)


class BatchCorrectionRequest(BaseModel):
    corrections: list[BatchCorrectionItem] = Field(..., min_length=1, max_length=100)


class UnmergeTrackletRequest(BaseModel):
    tracklet_id: str = Field(..., min_length=1, max_length=128)


class MergeGlobalTracksRequest(BaseModel):
    source_global_track_id: str = Field(..., min_length=1, max_length=128)
    target_global_track_id: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# POST /cts/identity/corrections
# ---------------------------------------------------------------------------


@router.post("/corrections")
async def apply_correction(
    body: CorrectionRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Apply a manual identity override.

    Proxies to :meth:`OrchestratorClient.manual_identity_override`. On
    success the orchestrator publishes an ``IdentityRevision`` on
    ``tracking.revisions``; the CC subscriber picks it up and rewrites the
    local history within one stream-read cycle (typically <200 ms).

    When ``annotation_id`` is set (M4 bbox tagging flow) and ``global_track_id``
    is empty, the call is recorded as a bbox-level correction without proxying
    to the orchestrator. Full gallery-update wiring lands in M5.
    """

    if body.annotation_id and not body.global_track_id:
        await client.tag_bbox_annotation(
            annotation_id=body.annotation_id,
            identity_id=body.new_identity_id,
            tagged_by=auth.name,
        )
        logger.info(
            "cts_bbox_tagged",
            actor=auth.name,
            annotation_id=body.annotation_id,
            new_identity_id=body.new_identity_id,
        )
        return {
            "revision_id": None,
            "annotation_id": body.annotation_id,
            "new_identity_id": body.new_identity_id,
            "status": "tagged",
        }

    try:
        resp = await client.manual_identity_override(
            global_track_id=body.global_track_id,
            new_identity_id=body.new_identity_id,
            actor=auth.name,
            reason=body.reason,
            display_name=body.display_name,
            evidence=body.evidence,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc

    revision_id = resp.get("revision_id")
    write_manual_revision_log(
        revision_id=revision_id,
        global_track_id=body.global_track_id,
        previous_identity_id=resp.get("previous_identity_id"),
        new_identity_id=body.new_identity_id,
        actor=auth.name,
        reason=body.reason,
        kind="manual_correct",
        evidence=body.evidence,
    )

    logger.info(
        "cts_identity_correction_applied",
        actor=auth.name,
        global_track_id=body.global_track_id,
        new_identity_id=body.new_identity_id,
        revision_id=revision_id,
    )
    return resp


# ---------------------------------------------------------------------------
# POST /cts/identity/merges
# ---------------------------------------------------------------------------


@router.post("/merges")
async def merge_identities(
    body: MergeRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Merge ``from_identity_id`` into ``to_identity_id`` for a global track.

    Implemented as a correction: the orchestrator revises ``global_track_id``
    to the target identity with ``reason="manual_merge"`` and evidence carrying
    both ids for audit.
    """
    try:
        resp = await client.manual_identity_override(
            global_track_id=body.global_track_id,
            new_identity_id=body.to_identity_id,
            actor=auth.name,
            reason=body.reason,
            evidence={
                "merge_from": body.from_identity_id,
                "merge_to": body.to_identity_id,
            },
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc

    revision_id = resp.get("revision_id")
    write_manual_revision_log(
        revision_id=revision_id,
        global_track_id=body.global_track_id,
        previous_identity_id=resp.get("previous_identity_id") or body.from_identity_id,
        new_identity_id=body.to_identity_id,
        actor=auth.name,
        reason=body.reason,
        kind="manual_merge",
        evidence={
            "merge_from": body.from_identity_id,
            "merge_to": body.to_identity_id,
        },
    )

    return resp


# ---------------------------------------------------------------------------
# POST /cts/identity/corrections/batch
# ---------------------------------------------------------------------------


@router.post("/corrections/batch")
async def apply_corrections_batch(
    body: BatchCorrectionRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct.batch")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Confirm multiple tracks as UNKNOWN (or assign to the same identity).

    Each correction is independent: one failure does not abort the batch.
    """
    results: list[dict[str, Any]] = []
    for item in body.corrections:
        try:
            resp = await client.manual_identity_override(
                global_track_id=item.global_track_id,
                new_identity_id=item.new_identity_id,
                actor=auth.name,
                reason=item.reason,
            )
            revision_id = resp.get("revision_id")
            write_manual_revision_log(
                revision_id=revision_id,
                global_track_id=item.global_track_id,
                previous_identity_id=resp.get("previous_identity_id"),
                new_identity_id=item.new_identity_id,
                actor=auth.name,
                reason=item.reason,
                kind="manual_correct",
                evidence=None,
            )
            results.append(
                {
                    "global_track_id": item.global_track_id,
                    "status": "ok",
                    "revision_id": revision_id,
                }
            )
        except UpstreamError as exc:
            logger.warning(
                "cts_identity_batch_item_upstream_error",
                global_track_id=item.global_track_id,
                error=str(exc),
            )
            results.append(
                {
                    "global_track_id": item.global_track_id,
                    "status": "error",
                    "error": str(exc),
                }
            )
        except Exception as exc:
            logger.exception(
                "cts_identity_batch_item_error",
                global_track_id=item.global_track_id,
            )
            results.append(
                {
                    "global_track_id": item.global_track_id,
                    "status": "error",
                    "error": str(exc),
                }
            )
    return {"results": results}


# ---------------------------------------------------------------------------
# POST /cts/identity/unmerge_tracklet
# ---------------------------------------------------------------------------


@router.post("/unmerge_tracklet", status_code=200)
async def unmerge_tracklet(
    body: UnmergeTrackletRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Detach a tracklet from its current global track.

    Proxies ``POST /internal/corrections/unmerge_tracklet`` on the
    tracking-orchestrator.  Returns ``tracklet_id``,
    ``original_global_track_id``, and ``new_global_track_id``.
    """
    try:
        data = await client.unmerge_tracklet(
            tracklet_id=body.tracklet_id,
            requested_by=auth.user_id,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return data


# ---------------------------------------------------------------------------
# POST /cts/identity/global_tracks/merge
# ---------------------------------------------------------------------------


@router.post("/global_tracks/merge", status_code=200)
async def merge_global_tracks(
    body: MergeGlobalTracksRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Merge source global track into target.

    Proxies ``POST /internal/corrections/merge_global_tracks`` on the
    tracking-orchestrator.  Returns ``source_id``, ``target_id``, and
    ``merged_at``.
    """
    try:
        data = await client.merge_global_tracks(
            source_id=body.source_global_track_id,
            target_id=body.target_global_track_id,
            merged_by=auth.user_id,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return data
