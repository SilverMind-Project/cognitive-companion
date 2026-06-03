"""
Occupancy API router - exposes unified room occupancy data and time-series.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.routers.dependencies import get_occupancy_read_model
from backend.services.occupancy import OccupancyReadModel

logger = get_logger(__name__)

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


@router.get("/")
async def get_occupancy(
    room_name: str | None = Query(None),
    auth: AuthContext = Depends(require_permission("caregiver")),
    model: OccupancyReadModel = Depends(get_occupancy_read_model),
):
    """Get current occupancy status for all occupied rooms (or a specific room).

    Returns a dict keyed by room name, with each entry containing:
    - ``occupied``: bool
    - ``since``: ISO timestamp when occupancy began, or null
    - ``source``: which system observed the room (``world_tracker``, ``ha_sensor``, ``pipeline``)
    - ``person_ids``: identified household member ids in the room
    - ``unknown_count``: unidentified hypotheses currently in the room
    - ``last_updated``: ISO timestamp of last observation
    """
    records = await model.get_occupancy(room_name=room_name)
    occupancy: dict[str, dict] = {}
    for rec in records:
        occupancy[rec.room_name] = {
            "room_name": rec.room_name,
            "room_id": rec.room_id,
            "occupied": rec.occupied,
            "since": rec.since.isoformat() if rec.since else None,
            "source": rec.source,
            "person_ids": rec.person_ids,
            "unknown_count": rec.unknown_count,
            "last_updated": rec.last_updated.isoformat() if rec.last_updated else None,
        }
    return {"occupancy": occupancy}


@router.get("/history")
async def get_occupancy_history(
    request: Request,
    room_name: str = Query(..., description="Room name"),
    hours: float = Query(2.0, description="Hours of history to fetch"),
    auth: AuthContext = Depends(require_permission("caregiver")),
):
    """Get smoothed occupancy time-series for a room from Home Assistant."""
    polling_service = getattr(request.app.state, "sensor_polling", None)
    if polling_service is None:
        return {"history": []}

    history = await polling_service.get_room_occupancy_timeseries(room_name, hours=hours)
    return {"room": room_name, "hours": hours, "history": history}
