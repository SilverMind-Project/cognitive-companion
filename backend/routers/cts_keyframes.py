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

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient

router = APIRouter(prefix="/cts/keyframes", tags=["cts-keyframes"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cts_enabled() -> None:
    if not settings.get("cts.enabled", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "cts.disabled", "message": "CTS is not enabled on this instance."},
        )


def _get_orchestrator_client() -> OrchestratorClient:
    return OrchestratorClient()


# ---------------------------------------------------------------------------
# Keyframe list
# ---------------------------------------------------------------------------


@router.get("")
async def list_keyframes(
    person_id: str | None = Query(None, description="Filter by person ID"),
    signal_type: str | None = Query(None, description="Filter by signal type"),
    after: str | None = Query(None, description="ISO-8601 timestamp"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """List tagged keyframes from the tracking-orchestrator."""
    _cts_enabled()
    keyframes = await client.list_keyframes(
        person_id=person_id,
        signal_type=signal_type,
        after=after,
        limit=limit,
    )
    return {"keyframes": keyframes, "count": len(keyframes)}


# ---------------------------------------------------------------------------
# Get one keyframe
# ---------------------------------------------------------------------------


@router.get("/{sample_id}")
async def get_keyframe(
    sample_id: str,
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Get a single tagged keyframe by sample ID."""
    _cts_enabled()
    try:
        keyframe = await client.get_keyframe(sample_id)
    except (HTTPException, UpstreamError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "keyframe.not_found", "message": f"Keyframe {sample_id} not found."},
        ) from e
    return keyframe


# ---------------------------------------------------------------------------
# Retain keyframe
# ---------------------------------------------------------------------------


@router.post("/{sample_id}/retain")
async def retain_keyframe(
    sample_id: str,
    _auth: AuthContext = Depends(require_permission("cts.keyframes.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Retain a keyframe past the normal retention window.

    This is used when a caregiver bookmarks a keyframe for later
    review or exports it for training.
    """
    _cts_enabled()
    try:
        result = await client.retain_keyframe(sample_id)
    except (HTTPException, UpstreamError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "keyframe.not_found", "message": f"Keyframe {sample_id} not found."},
        ) from e
    return {"retained": True, "sample_id": sample_id, "result": result}
