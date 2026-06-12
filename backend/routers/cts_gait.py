"""Gait trend BFF endpoint.

Route:
    GET /api/v1/cts/gait/trend?person_id=&days=

Proxies CTS gait daily aggregates through the GaitTrendService envelope so
the frontend never re-implements data quality gates or trend classification.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.routers.cts_deps import cts_enabled
from backend.schemas.gait import GaitTrendEnvelope
from backend.services.gait_trend_service import GaitTrendService

router = APIRouter(prefix="/cts/gait", tags=["cts-gait"])


def _get_service(request=None) -> GaitTrendService:
    from fastapi import Request

    from backend.integrations.tracking_orchestrator_client import OrchestratorClient

    return GaitTrendService(OrchestratorClient())


@router.get("/trend", response_model=GaitTrendEnvelope)
async def get_gait_trend(
    person_id: str = Query(..., description="Resident person ID"),
    days: int = Query(56, ge=14, le=365, description="Window length in days"),
    _auth: AuthContext = Depends(require_permission("cts.gait.trend.view")),
    svc: GaitTrendService = Depends(_get_service),
) -> GaitTrendEnvelope:
    """Return gait speed trend envelope for a resident."""
    cts_enabled()
    return await svc.get_gait_trend(person_id=person_id, days=days)
