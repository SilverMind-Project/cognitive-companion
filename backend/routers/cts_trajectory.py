"""CTS trajectory read endpoint proxied from the orchestrator."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.core.auth import require_permission
from backend.core.logging import get_logger
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_orchestrator_client

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-trajectory"])


@router.get(
    "/trajectory/recent",
    dependencies=[Depends(cts_enabled), Depends(require_permission("cts.view"))],
    summary="Proxy recent trajectory points from the orchestrator",
)
async def list_recent_trajectory(
    request: Request,
    identity_id: str | None = Query(None),
    since: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    client: OrchestratorClient = Depends(get_orchestrator_client),
) -> dict:
    """Return recent trajectory points for past-track annotation."""
    try:
        return await client.list_recent_trajectory(
            identity_id=identity_id, since=since, limit=limit
        )
    except Exception as exc:
        logger.exception("trajectory_proxy_error", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch trajectory data from orchestrator.",
        ) from exc
