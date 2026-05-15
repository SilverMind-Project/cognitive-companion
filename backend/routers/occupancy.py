"""
Occupancy API router - exposes room occupancy data and time-series.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.services.sensor_polling import SensorPollingService

logger = get_logger(__name__)

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


@router.get("/")
async def get_occupancy(
    request: Request,
    room_name: str | None = Query(None),
    auth: AuthContext = Depends(require_permission("caregiver")),
):
    """Get current occupancy status for all rooms (or a specific room)."""
    polling_service: SensorPollingService | None = request.app.state.sensor_polling
    if polling_service is None:
        return {"occupancy": {}}

    summary = await polling_service.get_occupancy_summary()
    if room_name:
        summary = {
            k: v for k, v in summary.items() if v.get("room", "").lower() == room_name.lower()
        }
    return {"occupancy": summary}


@router.get("/history")
async def get_occupancy_history(
    request: Request,
    room_name: str = Query(..., description="Room name"),
    hours: float = Query(2.0, description="Hours of history to fetch"),
    auth: AuthContext = Depends(require_permission("caregiver")),
):
    """Get smoothed occupancy time-series for a room from Home Assistant."""
    polling_service: SensorPollingService | None = request.app.state.sensor_polling
    if polling_service is None:
        return {"history": []}

    history = await polling_service.get_room_occupancy_timeseries(room_name, hours=hours)
    return {"room": room_name, "hours": hours, "history": history}
