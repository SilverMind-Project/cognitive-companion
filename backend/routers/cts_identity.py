"""CTS identity corrections + merges API.

Exposes the manual-override flow that underlies ``CTSIdentityCorrectionsView.vue``.
Requests are proxied through the :class:`OrchestratorClient`; the orchestrator
synthesizes an :class:`IdentityRevision` which flows back to CC through the
``tracking.revisions`` stream and the :class:`IdentityRewriter` service.

Endpoints
---------
- ``GET  /api/v1/cts/identity/global_tracks``: list currently-active global
  tracks with their committed identity, for the review table.
- ``POST /api/v1/cts/identity/corrections``: apply a manual override.
- ``POST /api/v1/cts/identity/merges``: merge two identities (sugar over
  corrections with both directions named).
- ``GET  /api/v1/cts/identity/revisions``: read recent revisions from the CC
  side for audit display.

When ``cts.enabled=False`` all handlers return 404 + ``{"code": "cts.disabled"}``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.integrations._upstream_base import UpstreamError
from backend.models.person import PersonLocationHistory

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/identity", tags=["cts-identity"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cts_enabled() -> None:
    if not settings.get("cts.enabled", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cts.disabled", "message": "CTS is not enabled on this instance."},
        )


def _get_orchestrator_client(request: Request) -> Any:
    client = getattr(request.app.state, "orchestrator_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "cts.orchestrator_unavailable"},
        )
    return client


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CorrectionRequest(BaseModel):
    global_track_id: str = Field(..., min_length=1, max_length=128)
    new_identity_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="manual", max_length=512)
    display_name: str | None = Field(default=None, max_length=128)
    evidence: dict[str, Any] = Field(default_factory=dict)


class MergeRequest(BaseModel):
    global_track_id: str = Field(..., min_length=1, max_length=128)
    from_identity_id: str = Field(..., min_length=1, max_length=128)
    to_identity_id: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="manual_merge", max_length=512)


# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks
# ---------------------------------------------------------------------------


@router.get("/global_tracks")
async def list_global_tracks(
    request: Request,
    open_only: bool = Query(True),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
) -> dict:
    """List current global tracks for the corrections review pane."""
    _cts_enabled()
    client = _get_orchestrator_client(request)
    try:
        tracks = await client.get_global_tracks(open_only=open_only)
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return {"tracks": tracks, "count": len(tracks)}


# ---------------------------------------------------------------------------
# POST /cts/identity/corrections
# ---------------------------------------------------------------------------


@router.post("/corrections")
async def apply_correction(
    body: CorrectionRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
) -> dict:
    """Apply a manual identity override.

    Proxies to :meth:`OrchestratorClient.manual_identity_override`. On
    success the orchestrator publishes an ``IdentityRevision`` on
    ``tracking.revisions``; the CC subscriber picks it up and rewrites the
    local history within one stream-read cycle (typically <200 ms).
    """
    _cts_enabled()
    client = _get_orchestrator_client(request)
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

    logger.info(
        "cts_identity_correction_applied",
        actor=auth.name,
        global_track_id=body.global_track_id,
        new_identity_id=body.new_identity_id,
        revision_id=resp.get("revision_id"),
    )
    return resp


# ---------------------------------------------------------------------------
# POST /cts/identity/merges
# ---------------------------------------------------------------------------


@router.post("/merges")
async def merge_identities(
    body: MergeRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
) -> dict:
    """Merge ``from_identity_id`` into ``to_identity_id`` for a global track.

    Implemented as a correction: the orchestrator revises ``global_track_id``
    to the target identity with ``reason="manual_merge"`` and evidence carrying
    both ids for audit.
    """
    _cts_enabled()
    client = _get_orchestrator_client(request)
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

    return resp


# ---------------------------------------------------------------------------
# GET /cts/identity/revisions
# ---------------------------------------------------------------------------


@router.get("/revisions")
async def list_revisions(
    window_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
) -> dict:
    """Return the CC-side audit log of applied revisions.

    The data source is the rewritten ``PersonLocationHistory`` rows (rows with
    a non-null ``superseded_by_revision_id``). Each distinct revision id in the
    result represents one applied revision; its earliest ``entered_at`` is used
    as the revision timestamp.
    """
    _cts_enabled()
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    db = get_session()
    try:
        rows = (
            db.query(PersonLocationHistory)
            .filter(
                PersonLocationHistory.superseded_by_revision_id.isnot(None),
                PersonLocationHistory.entered_at >= cutoff,
            )
            .order_by(PersonLocationHistory.entered_at.desc())
            .limit(limit * 5)  # headroom for the distinct-by-revision aggregation
            .all()
        )
    finally:
        db.close()

    by_revision: dict[str, dict[str, Any]] = {}
    for row in rows:
        rev_id = row.superseded_by_revision_id
        if rev_id is None:
            continue
        entry = by_revision.setdefault(
            rev_id,
            {
                "revision_id": rev_id,
                "previous_identity_id": row.person_id,
                "global_track_id": row.global_track_id,
                "earliest_entered_at": row.entered_at.isoformat() if row.entered_at else None,
                "rewritten_rows": 0,
            },
        )
        entry["rewritten_rows"] += 1
    return {
        "revisions": list(by_revision.values())[:limit],
        "count": len(by_revision),
        "window_hours": window_hours,
    }
