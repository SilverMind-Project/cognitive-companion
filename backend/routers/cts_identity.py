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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert

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

router = APIRouter(prefix="/cts/identity", tags=["cts-identity"])


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
    open_only: bool = Query(True),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int | None = Query(None, ge=0),
    camera_id: str | None = Query(None),
    track_status: str | None = Query(
        None,
        alias="status",
        pattern="^(committed|UNKNOWN)$",
    ),
    search: str | None = Query(None),
    include_transient: bool = Query(False, description="Include tracks shorter than min_duration_s"),
    min_duration_s: float = Query(10.0, ge=0.0, description="Hide UNKNOWN tracks shorter than this many seconds (ignored when include_transient=true)"),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """List current global tracks for the corrections review pane.

    Pagination via ``limit``/``offset``; filtering by ``camera_id``,
    ``status`` (committed / UNKNOWN), or free-text ``search`` over
    identity display name. UNKNOWN tracks shorter than ``min_duration_s``
    are hidden by default; set ``include_transient=true`` to reveal them.
    """
    cts_enabled()
    effective_min_duration = 0.0 if include_transient else min_duration_s
    try:
        data = await client.get_global_tracks(
            open_only=open_only,
            limit=limit,
            offset=offset,
            camera_id=camera_id,
            status=track_status,
            search=search,
            min_duration_s=effective_min_duration if effective_min_duration > 0 else None,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return {
        "tracks": data["tracks"],
        "count": data["count"],
        "limit": data.get("limit"),
        "offset": data.get("offset"),
    }


# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks/{id}
# ---------------------------------------------------------------------------


@router.get("/global_tracks/{global_track_id}")
async def get_global_track_detail(
    global_track_id: str,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return enriched detail for a single global track.

    Sources the track metadata from the orchestrator, posterior evidence
    from ``cts_identity_revision_log``, and camera dwell from CC side.
    """
    cts_enabled()
    try:
        track = await client.get_global_track(global_track_id)
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc

    # Enrich with posterior evidence from the revision log
    posterior = _latest_posterior(global_track_id)
    track["posterior"] = posterior

    return track


# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks/{id}/co_occurring
# ---------------------------------------------------------------------------


@router.get("/global_tracks/{global_track_id}/co_occurring")
async def list_co_occurring_tracks(
    global_track_id: str,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return other global tracks active at overlapping times/cameras."""
    cts_enabled()
    try:
        data = await client.get_global_tracks(open_only=True, limit=500, offset=0)
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc

    # Filter to tracks sharing a camera with the target, excluding self
    tracks = data["tracks"]
    target = None
    target_cameras: set[str] = set()
    for t in tracks:
        if t.get("global_track_id") == global_track_id:
            target = t
            target_cameras = set(t.get("camera_ids", []))
            break

    if target is None:
        return {"co_occurring": []}

    co_occurring = [
        t
        for t in tracks
        if t.get("global_track_id") != global_track_id
        and set(t.get("camera_ids", [])) & target_cameras
    ]
    return {"co_occurring": co_occurring, "count": len(co_occurring)}


# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks/{id}/keyframes
# ---------------------------------------------------------------------------


@router.get("/global_tracks/{global_track_id}/keyframes")
async def list_track_keyframes(
    global_track_id: str,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return up to 3 lifecycle keyframes for a global track."""
    cts_enabled()
    try:
        keyframes = await client.list_keyframes(
            global_track_id=global_track_id,
            limit=3,
            strategy="lifecycle",
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return {"keyframes": keyframes, "count": len(keyframes)}


# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks/{id}/trail
# ---------------------------------------------------------------------------


@router.get("/global_tracks/{global_track_id}/trail")
async def get_track_trail(
    global_track_id: str,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return the last 5 minutes of floor-point trail for a global track."""
    cts_enabled()
    try:
        trail_data = await client.list_recent_trajectory(
            global_track_id=global_track_id,
            limit=300,
        )
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return {
        "points": trail_data.get("points", []),
        "count": trail_data.get("count", 0),
    }


# ---------------------------------------------------------------------------
# GET /cts/identity/identities
# ---------------------------------------------------------------------------


@router.get("/identities")
async def list_identities(
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return all named identities for the identity picker in the corrections UI."""
    cts_enabled()
    try:
        identities = await client.get_identities()
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return {"identities": identities, "count": len(identities)}


# ---------------------------------------------------------------------------
# POST /cts/identity/corrections
# ---------------------------------------------------------------------------


@router.post("/corrections")
async def apply_correction(
    body: CorrectionRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Apply a manual identity override.

    Proxies to :meth:`OrchestratorClient.manual_identity_override`. On
    success the orchestrator publishes an ``IdentityRevision`` on
    ``tracking.revisions``; the CC subscriber picks it up and rewrites the
    local history within one stream-read cycle (typically <200 ms).
    """
    cts_enabled()
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
    _write_manual_revision_log(
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
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Merge ``from_identity_id`` into ``to_identity_id`` for a global track.

    Implemented as a correction: the orchestrator revises ``global_track_id``
    to the target identity with ``reason="manual_merge"`` and evidence carrying
    both ids for audit.
    """
    cts_enabled()
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
    _write_manual_revision_log(
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


class BatchCorrectionItem(BaseModel):
    global_track_id: str = Field(..., min_length=1, max_length=128)
    new_identity_id: str | None = Field(default=None, max_length=128)
    reason: str = Field(default="manual", max_length=512)


class BatchCorrectionRequest(BaseModel):
    corrections: list[BatchCorrectionItem] = Field(..., min_length=1, max_length=100)


@router.post("/corrections/batch")
async def apply_corrections_batch(
    body: BatchCorrectionRequest,
    auth: AuthContext = Depends(require_permission("cts.identity.correct.batch")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Confirm multiple tracks as UNKNOWN (or assign to the same identity).

    Each correction is independent: one failure does not abort the batch.
    """
    cts_enabled()
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
            _write_manual_revision_log(
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
# GET /cts/identity/health
# ---------------------------------------------------------------------------


@router.get("/health")
async def get_identity_health(
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Lightweight health snapshot for the identity/ReID subsystem.

    Never returns 5xx; upstream errors are surfaced in the ``issues`` list so
    the caregiver UI can display a non-blocking banner.
    """
    cts_enabled()
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
        issues.append(
            "ReID gallery is unreachable. The tracking orchestrator may be down."
        )

    return {
        "gallery_size": gallery_size,
        "upstream_ok": upstream_ok,
        "issues": issues,
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /cts/identity/enroll/batch
# ---------------------------------------------------------------------------


class BatchEnrollItem(BaseModel):
    tracklet_id: str = Field(..., min_length=1, max_length=128)
    identity_id: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)


class BatchEnrollRequest(BaseModel):
    items: list[BatchEnrollItem] = Field(..., min_length=1, max_length=50)


@router.post("/enroll/batch")
async def enroll_batch(
    body: BatchEnrollRequest,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Enroll multiple tracklets into the ReID gallery in a single request.

    Each item is independent: one failure does not abort the batch.  Enrollment
    is distinct from identity correction — it does not write to the revision log
    and does not synthesise a ``tracking.revisions`` stream message.
    """
    cts_enabled()
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
) -> dict:
    """Return the first-class identity decision log.

    Reads from ``cts_identity_revision_log``, which records every identity
    decision (auto from the resolver, manual from corrections/merges).

    Cursor pagination via ``before_id``: pass the ``revision_id`` of the last
    item on the current page to get the next page.
    """
    cts_enabled()
    db = get_session()
    try:
        query = db.query(CtsIdentityRevisionLog)
        if kind:
            query = query.filter(CtsIdentityRevisionLog.kind == kind)
        if before_id:
            # Keyset pagination: fetch the reference row's applied_at,
            # then rows with older timestamps (or same timestamp + lower id).
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
) -> dict:
    """Return the CC-side audit log of applied revisions.

    The data source is the rewritten ``PersonLocationHistory`` rows (rows with
    a non-null ``superseded_by_revision_id``). Each distinct revision id in the
    result represents one applied revision; its earliest ``entered_at`` is used
    as the revision timestamp.
    """
    cts_enabled()
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _latest_posterior(global_track_id: str) -> dict | None:
    """Fetch the latest posterior evidence for a global track from the log."""
    db = get_session()
    try:
        row = (
            db.query(CtsIdentityRevisionLog)
            .filter(
                CtsIdentityRevisionLog.global_track_id == global_track_id,
                CtsIdentityRevisionLog.evidence.isnot(None),
            )
            .order_by(CtsIdentityRevisionLog.applied_at.desc())
            .first()
        )
        if row is None or not row.evidence:
            return None
        return row.evidence
    finally:
        db.close()


def _write_manual_revision_log(
    *,
    revision_id: str | None,
    global_track_id: str,
    previous_identity_id: str | None,
    new_identity_id: str | None,
    actor: str,
    reason: str,
    kind: str,
    evidence: dict[str, Any] | None,
) -> None:
    """Write a preliminary manual identity decision to the audit log.

    Uses ON CONFLICT DO NOTHING: when the revision later flows back through
    the subscriber and the rewriter processes it, the rewriter's upsert will
    update ``rewritten_rows`` with the actual count while preserving the
    ``kind`` from this preliminary entry.
    """
    if not revision_id:
        logger.error("manual_revision_log_missing_revision_id")
        raise RuntimeError("Orchestrator correction response did not include revision_id")

    db = get_session()
    try:
        stmt = pg_insert(CtsIdentityRevisionLog).values(
            revision_id=revision_id,
            global_track_id=global_track_id,
            previous_identity_id=previous_identity_id,
            new_identity_id=new_identity_id,
            actor=actor,
            reason=reason,
            applied_at=datetime.now(UTC),
            kind=kind,
            rewritten_rows=0,
            evidence=evidence or {},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[CtsIdentityRevisionLog.revision_id],
            set_={
                "kind": kind,
                "actor": actor,
                "reason": reason,
            },
        )
        db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("manual_revision_log_write_error")
        raise
    finally:
        db.close()
