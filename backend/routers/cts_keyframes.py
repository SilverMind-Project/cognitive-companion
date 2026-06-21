"""CTS tagged keyframes API endpoints.

All handlers require ``cts.keyframes.view``.

Routes:
    GET    /api/v1/cts/keyframes             : list keyframes
    GET    /api/v1/cts/keyframes/{sample_id} : get one keyframe
    POST   /api/v1/cts/keyframes/{sample_id}/retain : retain past retention

When ``cts.enabled=false`` every handler returns 404 with code
``cts.disabled`` so no CTS code runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_session
from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.models.cts_signal import DementiaSignal
from backend.routers.cts_deps import cts_enabled, inject_image_urls
from backend.routers.dependencies import (
    get_keyframe_read_service,
    get_orchestrator_client,
)
from backend.services.cts.keyframe_read_service import (
    KeyframeReadContractError,
    KeyframeReadService,
)

router = APIRouter(prefix="/cts/keyframes", tags=["cts-keyframes"])


# ---------------------------------------------------------------------------
# Signal enrichment
# ---------------------------------------------------------------------------

_SIGNAL_WINDOW_HOURS = 2  # how far around a keyframe to look for signals


def _enrich_with_signals(keyframes: list[dict], person_ids: set[str]) -> list[dict]:
    """Join CC-side dementia signals onto keyframe dicts in-place.

    For each keyframe that has a ``person_id``, looks up the most recent
    dementia signal within ``_SIGNAL_WINDOW_HOURS`` and sets
    ``signal_type``, ``severity``, and ``signal_id`` on the dict.
    """
    if not keyframes or not person_ids:
        return keyframes

    db = get_session()
    try:
        stmt = (
            select(DementiaSignal)
            .where(DementiaSignal.person_id.in_(person_ids))
            .order_by(DementiaSignal.window_start.desc())
            .limit(500)
        )
        signals = list(db.scalars(stmt).all())
    finally:
        db.close()

    if not signals:
        return keyframes

    # Index signals by person_id for faster lookup.
    signals_by_person: dict[str, list[DementiaSignal]] = {}
    for s in signals:
        signals_by_person.setdefault(s.person_id, []).append(s)

    for kf in keyframes:
        pid = kf.get("person_id")
        if not pid or pid not in signals_by_person:
            continue

        captured_str = kf.get("captured_at")
        if not captured_str:
            continue
        try:
            captured_at = datetime.fromisoformat(captured_str)
        except ValueError, TypeError:
            continue

        window_start = captured_at - timedelta(hours=_SIGNAL_WINDOW_HOURS)
        window_end = captured_at + timedelta(hours=_SIGNAL_WINDOW_HOURS)

        # Find the closest signal in time within the window.
        best: DementiaSignal | None = None
        best_delta = timedelta.max
        for sig in signals_by_person[pid]:
            if sig.window_start is None:
                continue
            if window_start <= sig.window_start <= window_end:
                delta = abs((sig.window_start - captured_at).total_seconds())
                if delta < best_delta.total_seconds():
                    best = sig
                    best_delta = timedelta(seconds=delta)

        if best is not None:
            kf["signal_type"] = best.signal_type
            kf["severity"] = best.severity
            kf["signal_id"] = best.signal_id

    return keyframes


# ---------------------------------------------------------------------------
# Keyframe list
# ---------------------------------------------------------------------------


@router.get("")
async def list_keyframes(
    request: Request,
    person_id: str | None = Query(
        None, description="Effective household identity (frame matches any bbox)"
    ),
    camera_id: str | None = Query(None, description="Filter by camera"),
    tag_reason: str | None = Query(None, description="Filter by trigger reason"),
    after: str | None = Query(None, description="ISO-8601 start time"),
    before: str | None = Query(None, description="ISO-8601 end time"),
    explicit_unknown: bool = Query(False, description="Only frames with an Unknown bbox"),
    authority: str | None = Query(None, description="Match any bbox with this authority"),
    decision_source: str | None = Query(None, description="Match any bbox source"),
    conflict_only: bool = Query(False, description="Only frames with a conflict"),
    pending_review_only: bool = Query(False, description="Only frames pending ReID review"),
    limit: int = Query(50, ge=1, le=200, description="Max physical-frame cards"),
    offset: int = Query(0, ge=0),
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    svc: KeyframeReadService = Depends(get_keyframe_read_service),
) -> dict:
    """List keyframes grouped into one card per physical source frame (M07).

    Each card carries every visible bbox with server-owned effective identity,
    a card summary, and explicit Unknown/conflict/pending counts. Filtering and
    pagination are server-side; a matching frame still returns all of its bboxes
    for context.
    """
    cts_enabled()
    try:
        page = await svc.list_frames(
            camera_id=camera_id,
            tag_reason=tag_reason,
            after=after,
            before=before,
            effective_identity_id=person_id,
            explicit_unknown=explicit_unknown,
            authority=authority,
            decision_source=decision_source,
            conflict_only=conflict_only,
            pending_review_only=pending_review_only,
            limit=limit,
            offset=offset,
        )
    except KeyframeReadContractError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "keyframe.upstream_contract",
                "message": "Upstream keyframe envelope was malformed.",
            },
        ) from exc

    keyframes = [card.model_dump(mode="json") for card in page.keyframes]
    keyframes = inject_image_urls(keyframes, request)
    return {
        "keyframes": keyframes,
        "count": page.count,
        "total": page.total,
        "truncated": page.truncated,
        "limit": page.limit,
        "offset": page.offset,
    }


# ---------------------------------------------------------------------------
# Get one keyframe
# ---------------------------------------------------------------------------


@router.get("/{sample_id}")
async def get_keyframe(
    sample_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Get a single tagged keyframe by sample ID."""
    cts_enabled()
    try:
        keyframe = await client.get_keyframe(sample_id)
    except (HTTPException, UpstreamError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "keyframe.not_found", "message": f"Keyframe {sample_id} not found."},
        ) from e
    return inject_image_urls(
        _enrich_with_signals([keyframe], {keyframe.get("person_id") or ""} - {""}),
        request,
    )[0]


# ---------------------------------------------------------------------------
# Retain keyframe
# ---------------------------------------------------------------------------


@router.post("/{sample_id}/retain")
async def retain_keyframe(
    sample_id: str,
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Retain a keyframe past the normal retention window.

    This is used when a caregiver bookmarks a keyframe for later
    review or exports it for training.
    """
    cts_enabled()
    try:
        result = await client.retain_keyframe(sample_id)
    except (HTTPException, UpstreamError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "keyframe.not_found", "message": f"Keyframe {sample_id} not found."},
        ) from e
    return {"retained": True, "sample_id": sample_id, "result": result}
