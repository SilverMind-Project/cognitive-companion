"""
Occupancy API router - exposes unified room occupancy data and time-series.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.models.occupancy import RoomOccupancyState

logger = get_logger(__name__)

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


@router.get("/")
async def get_occupancy(
    room_name: str | None = Query(None),
    auth: AuthContext = Depends(require_permission("caregiver")),
    db=Depends(get_session),
):
    """Get current occupancy status for all rooms (or a specific room).

    Returns a dict keyed by room name, with each entry containing:
    - ``occupied``: bool
    - ``since``: ISO timestamp when occupancy began, or null
    - ``source``: which system last updated this room (``cts``, ``ha_sensor``, ``pipeline``)
    - ``person_ids``: list of identified person IDs in the room (empty for ha_sensor)
    - ``last_updated``: ISO timestamp of last state change
    """
    query = db.query(RoomOccupancyState)
    if room_name:
        query = query.filter(RoomOccupancyState.room_name == room_name)
    rows = query.order_by(RoomOccupancyState.room_name).all()

    occupancy: dict[str, dict] = {}
    for row in rows:
        occupancy[row.room_name] = {
            "room_name": row.room_name,
            "occupied": row.occupied,
            "since": row.since.isoformat() if row.since else None,
            "source": row.source,
            "person_ids": row.person_ids or [],
            "last_updated": row.last_updated.isoformat() if row.last_updated else None,
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
