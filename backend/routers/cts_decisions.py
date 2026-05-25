"""CTS identity decisions, revisions, health, and batch enrollment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.integrations._upstream_base import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.cts_identity_revision_log import CtsIdentityRevisionLog
from backend.models.person import PersonLocationHistory
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_orchestrator_client

logger = get_logger(__name__)

router = APIRouter(prefix="/cts/identity", tags=["cts-decisions"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BatchEnrollItem(BaseModel):
    tracklet_id: str = Field(..., min_length=1, max_length=128)
    identity_id: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)


class BatchEnrollRequest(BaseModel):
    items: list[BatchEnrollItem] = Field(..., min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# GET /cts/identity/health
# ---------------------------------------------------------------------------


@router.get("/health")
async def get_identity_health(
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Lightweight health snapshot for the identity/ReID subsystem.

    Never returns 5xx; upstream errors are surfaced in the ``issues`` list so
    the caregiver UI can display a non-blocking banner.
    """
    issues: list[str] = []
    gallery_size = 0
    upstream_ok = False

    try:
        identities = await client.get_identities(active_only=False)
        gallery_size = len(identities)
        upstream_ok = True
        if gallery_size == 0:
            issues.append(
                "No named identities in the ReID gallery — "
                "use 'Enroll in gallery' on a keyframe to seed appearance embeddings."
            )
    except Exception:
        logger.warning("cts_identity_health_upstream_error", exc_info=True)
        issues.append("ReID gallery is unreachable. The tracking orchestrator may be down.")

    return {
        "gallery_size": gallery_size,
        "upstream_ok": upstream_ok,
        "issues": issues,
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /cts/identity/enroll/batch
# ---------------------------------------------------------------------------


@router.post("/enroll/batch")
async def enroll_batch(
    body: BatchEnrollRequest,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Enroll multiple tracklets into the ReID gallery in a single request.

    Each item is independent: one failure does not abort the batch.  Enrollment
    is distinct from identity correction — it does not write to the revision log
    and does not synthesise a ``tracking.revisions`` stream message.
    """
    results: list[dict[str, Any]] = []
    for item in body.items:
        try:
            resp = await client.enroll_from_tracklet(
                identity_id=item.identity_id,
                tracklet_id=item.tracklet_id,
                display_name=item.display_name,
            )
            results.append(
                {
                    "tracklet_id": item.tracklet_id,
                    "identity_id": item.identity_id,
                    "status": "ok",
                    "enrolled_count": resp.get("enrolled_count", 0),
                }
            )
        except UpstreamError as exc:
            logger.warning(
                "cts_enroll_batch_item_upstream_error",
                tracklet_id=item.tracklet_id,
                error=str(exc),
            )
            results.append(
                {
                    "tracklet_id": item.tracklet_id,
                    "identity_id": item.identity_id,
                    "status": "error",
                    "error": str(exc),
                }
            )
        except Exception as exc:
            logger.exception(
                "cts_enroll_batch_item_error",
                tracklet_id=item.tracklet_id,
            )
            results.append(
                {
                    "tracklet_id": item.tracklet_id,
                    "identity_id": item.identity_id,
                    "status": "error",
                    "error": str(exc),
                }
            )
    return {"results": results}


# ---------------------------------------------------------------------------
# GET /cts/identity/decisions
# ---------------------------------------------------------------------------


@router.get("/decisions")
async def list_decisions(
    kind: str | None = Query(None, pattern="^(auto|manual_correct|manual_merge)$"),
    limit: int = Query(50, ge=1, le=200),
    before_id: str | None = Query(None),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
) -> dict:
    """Return the first-class identity decision log.

    Reads from ``cts_identity_revision_log``, which records every identity
    decision (auto from the resolver, manual from corrections/merges).

    Cursor pagination via ``before_id``: pass the ``revision_id`` of the last
    item on the current page to get the next page.
    """
    db = get_session()
    try:
        query = db.query(CtsIdentityRevisionLog)
        if kind:
            query = query.filter(CtsIdentityRevisionLog.kind == kind)
        if before_id:
            ref = query.filter(CtsIdentityRevisionLog.revision_id == before_id).first()
            if ref is not None:
                query = query.filter(
                    (CtsIdentityRevisionLog.applied_at < ref.applied_at)
                    | (
                        (CtsIdentityRevisionLog.applied_at == ref.applied_at)
                        & (CtsIdentityRevisionLog.revision_id < ref.revision_id)
                    ),
                )
        query = query.order_by(
            CtsIdentityRevisionLog.applied_at.desc(),
            CtsIdentityRevisionLog.revision_id.desc(),
        )
        rows = query.limit(limit + 1).all()
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
    finally:
        db.close()

    return {
        "decisions": [
            {
                "revision_id": r.revision_id,
                "global_track_id": r.global_track_id,
                "previous_identity_id": r.previous_identity_id,
                "new_identity_id": r.new_identity_id,
                "actor": r.actor,
                "reason": r.reason,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
                "kind": r.kind,
                "rewritten_rows": r.rewritten_rows,
                "evidence": r.evidence,
            }
            for r in rows
        ],
        "count": len(rows),
        "has_more": has_more,
    }


# ---------------------------------------------------------------------------
# GET /cts/identity/revisions
# ---------------------------------------------------------------------------


@router.get("/revisions")
async def list_revisions(
    window_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(100, ge=1, le=500),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
) -> dict:
    """Return the CC-side audit log of applied revisions.

    The data source is the rewritten ``PersonLocationHistory`` rows (rows with
    a non-null ``superseded_by_revision_id``). Each distinct revision id in the
    result represents one applied revision; its earliest ``entered_at`` is used
    as the revision timestamp.
    """
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
