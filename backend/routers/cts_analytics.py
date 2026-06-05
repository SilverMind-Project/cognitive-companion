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
    start_minute: int | None = Query(None, ge=0, le=1439),
    end_minute: int | None = Query(None, ge=0, le=1439),
    svc: PersonLocationService = Depends(get_person_location_service),
    _auth: AuthContext = Depends(require_permission("cts.analytics.heatmap.view")),
) -> HeatmapEnvelope:
    """Return aggregated floor-plan heatmap bins for a person over a time range.

    ``start_minute`` and ``end_minute`` (0-1439, minutes since *local* midnight
    in ``app.timezone``) restrict which time-of-day buckets contribute to the
    density map. When ``start_minute > end_minute`` the window wraps past
    midnight (e.g. 22:00-03:00 for sundowning behaviours). Both bounds must be
    supplied together, or neither (no time-of-day filter).
    """
    if start_time >= end_time:
        raise ValidationError("start_time must be before end_time")
    if (start_minute is None) != (end_minute is None):
        raise ValidationError("start_minute and end_minute must be supplied together")
    return await svc.get_heatmap(
        person_id=person_id,
        start_time=start_time,
        end_time=end_time,
        filter_start_minute=start_minute,
        filter_end_minute=end_minute,
    )
