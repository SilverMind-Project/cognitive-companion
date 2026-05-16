"""RoomRenameService: cascades Room renames to linked CtsCamera rows.

When a Room is renamed or deleted, the ``room_name`` on every linked
``CtsCamera`` must be updated so downstream consumers (rtsp-ingress
reconciler, orchestrator tracking events) see the correct name.

This service is intended to be called from the Room update/delete
endpoints and the maintain-setup command.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.cts_camera import CtsCamera

logger = get_logger(__name__)


def on_room_renamed(db: Session, room_id: int, new_name: str) -> int:
    """Update ``room_name`` on every ``CtsCamera`` linked to *room_id*.

    Returns the number of cameras updated.
    """
    cameras = (
        db.query(CtsCamera).filter(CtsCamera.room_id == room_id).all()
    )
    for cam in cameras:
        cam.room_name = new_name
    if cameras:
        db.flush()
        logger.info(
            "room_rename_cascade",
            room_id=room_id,
            new_name=new_name,
            camera_count=len(cameras),
        )
    return len(cameras)


def on_room_deleted(db: Session, room_id: int) -> int:
    """Clear ``room_id`` on every ``CtsCamera`` linked to *room_id*.

    ``room_name`` is preserved as a tombstone so downstream consumers
    still see a meaningful string.
    """
    cameras = (
        db.query(CtsCamera).filter(CtsCamera.room_id == room_id).all()
    )
    for cam in cameras:
        cam.room_id = None
    if cameras:
        db.flush()
        logger.info(
            "room_delete_cascade",
            room_id=room_id,
            camera_count=len(cameras),
        )
    return len(cameras)
