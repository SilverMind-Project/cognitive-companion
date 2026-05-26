"""CTS global track listing, detail, and identity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.core.auth import AuthContext, require_permission
from backend.integrations._upstream_base import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled, inject_image_urls
from backend.routers.cts_identity_helpers import latest_posterior
from backend.routers.dependencies import get_orchestrator_client

router = APIRouter(prefix="/cts/identity", tags=["cts-tracks"])

# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks
# ---------------------------------------------------------------------------


@router.get("/global_tracks")
async def list_global_tracks(
    open_only: bool = Query(True),
    since: str | None = Query(
        None,
        description="ISO-8601 timestamp; include closed tracks last seen at or after this time",
    ),
    limit: int | None = Query(None, ge=1, le=500),
    offset: int | None = Query(None, ge=0),
    camera_id: str | None = Query(None),
    identity_id: str | None = Query(None, description="Filter to tracks assigned this identity"),
    track_status: str | None = Query(
        None,
        alias="status",
        pattern="^(committed|UNKNOWN)$",
    ),
    search: str | None = Query(None),
    include_transient: bool = Query(
        False, description="Include tracks shorter than min_duration_s"
    ),
    min_duration_s: float = Query(
        10.0,
        ge=0.0,
        description="Hide UNKNOWN tracks shorter than this many seconds (ignored when include_transient=true)",
    ),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """List global tracks for the corrections review pane.

    Pagination via ``limit``/``offset``; filtering by ``camera_id``,
    ``status`` (committed / UNKNOWN), or free-text ``search`` over
    identity display name. UNKNOWN tracks shorter than ``min_duration_s``
    are hidden by default; set ``include_transient=true`` to reveal them.
    Pass ``since`` + ``open_only=false`` to retrieve today's full history
    including closed tracks.
    """
    effective_min_duration = 0.0 if include_transient else min_duration_s
    try:
        data = await client.get_global_tracks(
            open_only=open_only,
            since=since,
            limit=limit,
            offset=offset,
            camera_id=camera_id,
            identity_id=identity_id,
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
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return enriched detail for a single global track.

    Sources the track metadata from the orchestrator, posterior evidence
    from ``cts_identity_revision_log``, and camera dwell from CC side.
    """
    try:
        track = await client.get_global_track(global_track_id)
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc

    posterior = latest_posterior(global_track_id) or track.get("last_posterior_jsonb")
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
    _cts: None = Depends(cts_enabled),
) -> dict:
    """Return other global tracks active at overlapping times/cameras."""
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
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return up to 3 lifecycle keyframes for a global track."""
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
    keyframes = inject_image_urls(keyframes, request)
    return {"keyframes": keyframes, "count": len(keyframes)}


# ---------------------------------------------------------------------------
# GET /cts/identity/global_tracks/{id}/trail
# ---------------------------------------------------------------------------


@router.get("/global_tracks/{global_track_id}/trail")
async def get_track_trail(
    global_track_id: str,
    since: str | None = Query(
        None,
        description="ISO-8601 timestamp; return trajectory points observed at or after this time",
    ),
    _auth: AuthContext = Depends(require_permission("cts.identity.correct")),
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return posture trajectory points for a global track."""
    try:
        trail_data = await client.list_recent_trajectory(
            global_track_id=global_track_id,
            since=since,
            limit=500,
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
    _cts: None = Depends(cts_enabled),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return all named identities for the identity picker in the corrections UI."""
    try:
        identities = await client.get_identities()
    except UpstreamError as exc:
        raise HTTPException(
            status_code=exc.status or status.HTTP_502_BAD_GATEWAY,
            detail={"code": "cts.upstream_error", "message": str(exc)},
        ) from exc
    return {"identities": identities, "count": len(identities)}
