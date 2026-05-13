"""CTS dashboard proxy endpoints.

Proxies the three dashboard endpoints and the keyframe query endpoint
from the tracking-orchestrator to the frontend.

Routes:
    GET /api/v1/cts/dashboard/signals
    GET /api/v1/cts/dashboard/trajectory
    GET /api/v1/cts/dashboard/dwell_summary
    GET /api/v1/cts/keyframes          (already in cts_keyframes.py: not duplicated)

When ``cts.enabled=false`` every handler returns 404 with code
``cts.disabled``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled

router = APIRouter(prefix="/cts/dashboard", tags=["cts-dashboard"])


def _get_orchestrator_client() -> OrchestratorClient:
    return OrchestratorClient()


# ---------------------------------------------------------------------------
# GET /cts/dashboard/signals
# ---------------------------------------------------------------------------


@router.get("/signals")
async def get_signals(
    person_id: str | None = Query(None, description="Filter by person ID"),
    window_hours: int = Query(24, ge=1, le=720, description="Lookback window in hours"),
    signal_kind: str | None = Query(None, description="Filter by signal kind"),
    limit: int = Query(200, ge=1, le=1000),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return recent dementia signals from the orchestrator."""
    cts_enabled()
    return await client.get_dashboard_signals(
        person_id=person_id,
        window_hours=window_hours,
        signal_kind=signal_kind,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /cts/dashboard/trajectory
# ---------------------------------------------------------------------------


@router.get("/trajectory")
async def get_trajectory(
    person_id: str = Query(..., description="Person ID (required)"),
    start: str | None = Query(None, description="ISO-8601 start time"),
    end: str | None = Query(None, description="ISO-8601 end time"),
    limit: int = Query(500, ge=1, le=5000),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return trajectory points for floor-plan overlay."""
    cts_enabled()
    return await client.get_dashboard_trajectory(
        person_id=person_id,
        start=start,
        end=end,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /cts/dashboard/dwell_summary
# ---------------------------------------------------------------------------


@router.get("/dwell_summary")
async def get_dwell_summary(
    person_id: str = Query(..., description="Person ID (required)"),
    date: str | None = Query(None, description="ISO-8601 date (YYYY-MM-DD); defaults to today"),
    _auth: AuthContext = Depends(require_permission("cts.signals.view")),
    client: OrchestratorClient = Depends(_get_orchestrator_client),
) -> dict:
    """Return room dwell aggregation (time-in-room) for one day."""
    cts_enabled()
    return await client.get_dashboard_dwell_summary(
        person_id=person_id,
        date=date,
    )
