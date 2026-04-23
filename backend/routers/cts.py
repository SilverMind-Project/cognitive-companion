"""CTS feature-flag and system status endpoints.

GET /api/v1/cts/status   — overall CTS status for the UI status bar
GET /api/v1/cts/features — feature flags visible to the frontend
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings

router = APIRouter(prefix="/cts", tags=["cts"])


@router.get("/status")
async def get_status(
    _auth: AuthContext = Depends(require_permission("cts.view")),
) -> dict:
    """Return a top-level CTS health snapshot."""
    return {
        "enabled": bool(settings.get("cts.enabled", False)),
        "calibration_enabled": bool(settings.get("cts_ui.calibration_enabled", True)),
        "dashboard_enabled": bool(settings.get("cts_ui.dashboard_enabled", True)),
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
