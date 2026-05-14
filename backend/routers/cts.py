"""CTS feature-flag and system status endpoints.

GET /api/v1/cts/status          : live CTS health (orchestrator + subscribers)
GET /api/v1/cts/features        : feature flags visible to the frontend
"""

from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Depends, Request

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts"])


@router.get("/status")
async def get_status(
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.view")),
) -> dict:
    """Live CTS health snapshot: orchestrator reachability + subscriber states."""
    orch_client = getattr(request.app.state, "orchestrator_client", None)
    cts_runtime = getattr(request.app.state, "cts_runtime", None)

    orchestrator: dict = {"reachable": False, "error": None}
    if orch_client is not None:
        try:
            orch_health = await orch_client.get_health()
            orchestrator["reachable"] = True
            orchestrator["health"] = orch_health
        except Exception as exc:
            orchestrator["error"] = str(exc)

    subscribers = None
    if cts_runtime is not None:
        with suppress(Exception):
            subscribers = cts_runtime.status()["subscribers"]

    return {
        "enabled": bool(settings.get("cts.enabled", False)),
        "orchestrator": orchestrator,
        "subscribers": subscribers,
    }


@router.get("/features")
async def get_features(
    _auth: AuthContext = Depends(require_permission("cts.view")),
) -> dict:
    """Return feature-flag toggles for the frontend to gate UI sections."""
    return {
        "calibration": bool(settings.get("cts_ui.calibration_enabled", True)),
        "live_view": bool(settings.get("cts_ui.live_view_enabled", False)),
        "signals_dashboard": bool(settings.get("cts_ui.dashboard_enabled", True)),
    }



