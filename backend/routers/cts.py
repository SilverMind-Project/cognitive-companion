"""CTS feature-flag, system status, and frame-serving endpoints.

GET /api/v1/cts/status          : live CTS health (orchestrator + subscribers)
GET /api/v1/cts/features        : feature flags visible to the frontend
GET /api/v1/cts/frames/{key}    : proxy a CTS frame from MinIO (browser-safe)
"""

from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.core.auth import AuthContext, require_permission
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_deps import cts_enabled
from backend.routers.dependencies import get_minio_client
from backend.services.cts.runtime import CTSRuntime

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts"])


@router.get("/status")
async def get_status(
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.view")),
) -> dict:
    """Live CTS health snapshot: orchestrator reachability + subscriber states."""
    orch_client: OrchestratorClient | None = getattr(
        request.app.state, "orchestrator_client", None
    )
    cts_runtime: CTSRuntime | None = getattr(request.app.state, "cts_runtime", None)

    orchestrator: dict = {"reachable": False, "error": None}
    if orch_client is not None:
        try:
            orch_health = await orch_client.get_health()
            orchestrator["reachable"] = True
            orchestrator["health"] = orch_health
        except Exception as exc:  # noqa: BLE001
            orchestrator["error"] = str(exc)

    subscribers = None
    if cts_runtime is not None:
        with suppress(Exception):
            subscribers = cts_runtime.status()["subscribers"]

    return {
        "enabled": settings.as_bool("cts.enabled"),
        "calibration_enabled": settings.as_bool("cts_ui.calibration_enabled"),
        "dashboard_enabled": settings.as_bool("cts_ui.dashboard_enabled"),
        "live_view_enabled": settings.as_bool("cts_ui.live_view_enabled"),
        "orchestrator": orchestrator,
        "subscribers": subscribers,
    }


@router.get("/features")
async def get_features(
    _auth: AuthContext = Depends(require_permission("cts.view")),
) -> dict:
    """Return feature-flag toggles for the frontend to gate UI sections."""
    return {
        "calibration": settings.as_bool("cts_ui.calibration_enabled"),
        "live_view": settings.as_bool("cts_ui.live_view_enabled"),
        "signals_dashboard": settings.as_bool("cts_ui.dashboard_enabled"),
    }


@router.get("/frames/{key:path}")
async def get_frame(
    key: str,
    request: Request,
    _auth: AuthContext = Depends(require_permission("cts.cameras.read")),
    minio: MinioClient = Depends(get_minio_client),
) -> Response:
    """Proxy a CTS frame JPEG from MinIO.

    The live-view browser may not be able to reach MinIO directly (e.g.
    Docker-internal hostnames), so it loads frames through this endpoint.
    The frame is fetched server-side and returned as image bytes.
    """
    cts_enabled()
    image_bytes = await minio.async_get_object(key)
    if image_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "frame.not_found", "message": f"Frame {key} not found."},
        )
    return Response(content=image_bytes, media_type="image/jpeg")
