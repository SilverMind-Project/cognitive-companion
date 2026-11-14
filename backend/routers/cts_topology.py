"""Learned camera-to-camera handoffs (read-only).

CTS records every accepted cross-camera handoff: how many there were per ordered camera pair
and the delay between the earlier track's close and the new sighting. The delay is measured
from the close, which comes at least the close grace after the last sighting, so it is not a
walk time. Operators do not edit these; the Shared Views page shows them beside the groups.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.auth import AuthContext, require_permission
from backend.core.upstream_errors import UpstreamError
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_orchestrator_client

router = APIRouter(prefix="/cts/topology", tags=["cts-topology"])


class LearnedTransitionOut(BaseModel):
    from_camera: str
    to_camera: str
    observation_count: int
    mean_transit_s: float
    std_transit_s: float
    last_updated_at: datetime | None


class LearnedTransitionsOut(BaseModel):
    transitions: list[LearnedTransitionOut]


@router.get("/transitions", response_model=LearnedTransitionsOut)
async def learned_transitions(
    orchestrator: OrchestratorClient = Depends(get_orchestrator_client),
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> LearnedTransitionsOut:
    """Return the handoffs CTS has learned between cameras, most observed first."""
    cts_enabled()
    try:
        payload = await orchestrator.learned_transitions()
    except UpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": str(exc.code), "service": exc.service, "message": str(exc)},
        ) from exc
    return LearnedTransitionsOut.model_validate(payload)
