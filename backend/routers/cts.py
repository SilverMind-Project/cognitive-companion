"""CTS feature-flag, system status, and frame-serving endpoints.

GET /api/v1/cts/status          : live CTS health (orchestrator + subscribers)
GET /api/v1/cts/features        : feature flags visible to the frontend
GET /api/v1/cts/frames/{key}    : redirect to a presigned MinIO URL for a CTS frame
"""

from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.routers.cts_deps import cts_enabled

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


@router.get("/frames/{key:path}")
def get_frame(
    key: str,
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
) -> Response:
    """Redirect to a short-lived MinIO presigned URL for a CTS frame JPEG.

    The live view cannot reach MinIO directly, so the browser loads
    GET /api/v1/cts/frames/{minio_key}?api_key=... and follows this 302
    to the presigned URL. TTL is 120 s — enough for a displayed frame to
    load while short enough to limit stale-URL misuse.
    """
    cts_enabled()
    minio = getattr(request.app.state, "minio_client", None)
    if minio is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "minio.unavailable", "message": "Object storage not configured."},
        )
    url: str = minio.generate_presigned_url(key, expiration=120)
    return Response(status_code=302, headers={"Location": url})
