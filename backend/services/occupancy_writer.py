"""Shared helper for upserting the unified RoomOccupancyState table.

Both SensorPollingService (HA presence sensors) and CTS camera tracking
call this to keep room occupancy in sync regardless of
which data source detected the change.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.occupancy import RoomOccupancyState

logger = get_logger(__name__)


def upsert_room_occupancy(
    db: Session,
    *,
    room_name: str,
    occupied: bool,
    source: str,
    person_ids: list[str] | None = None,
    since: datetime | None = None,
) -> None:
    """Create or update the occupancy state for *room_name* and commit.

    Parameters
    ----------
    db:
        An active SQLAlchemy session.  This function commits the session.
    room_name:
        The canonical room name (used as primary key).
    occupied:
        Whether the room is currently occupied.
    source:
        Data source that produced this update: ``'cts'``, ``'ha_sensor'``,
        or ``'pipeline'``.
    person_ids:
        List of identified person IDs in the room.  Pass an empty list when
        the source (e.g. ha_sensor) cannot identify individuals.
    since:
        When the current occupancy window began.  Defaults to *now* when
        transitioning to occupied.  Ignored when transitioning to unoccupied.
    """
    now = datetime.now(UTC)
    row: RoomOccupancyState | None = (
        db.query(RoomOccupancyState).filter_by(room_name=room_name).first()
    )
    if row is None:
        row = RoomOccupancyState(
            room_name=room_name,
            occupied=occupied,
            since=(since or now) if occupied else None,
            source=source,
            person_ids=person_ids or [],
            last_updated=now,
        )
        db.add(row)
    else:
        if occupied and not row.occupied:
            row.since = since or now
        elif not occupied:
            row.since = None
        row.occupied = occupied
        row.source = source
        row.person_ids = person_ids or []
        row.last_updated = now
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("room_occupancy_upsert_error", room=room_name)
        raise
