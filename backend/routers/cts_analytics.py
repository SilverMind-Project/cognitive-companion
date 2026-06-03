"""CTS analytics endpoints (heatmap density, etc.)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from backend.core.auth import AuthContext, require_permission
from backend.core.exceptions import ValidationError
from backend.routers.dependencies import get_person_location_service
from backend.schemas.cts_analytics import HeatmapEnvelope
from backend.services.person_location.service import PersonLocationService

router = APIRouter(prefix="/api/v1/cts/analytics", tags=["cts-analytics"])


@router.get("/heatmap", response_model=HeatmapEnvelope)
async def get_heatmap(
    person_id: str,
    start_time: datetime,
    end_time: datetime,
    start_hour: int | None = Query(None, ge=0, le=23),
    end_hour: int | None = Query(None, ge=0, le=23),
    svc: PersonLocationService = Depends(get_person_location_service),
    _auth: AuthContext = Depends(require_permission("cts.analytics.heatmap.view")),
) -> HeatmapEnvelope:
    """Return aggregated floor-plan heatmap bins for a person over a time range.

    ``start_hour`` and ``end_hour`` (0-23, UTC) restrict which time-of-day
    buckets contribute to the density map (e.g. daytime-only heatmaps).
    """
    if start_time >= end_time:
        raise ValidationError("start_time must be before end_time")
    return await svc.get_heatmap(
        person_id=person_id,
        start_time=start_time,
        end_time=end_time,
        filter_start_hour=start_hour,
        filter_end_hour=end_hour,
    )
