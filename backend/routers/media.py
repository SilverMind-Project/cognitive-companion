"""
Media buffer endpoints -- exposes per-camera in-flight and recently flushed
images from the EventAggregator / MediaCache for the admin console.

GET /api/v1/media/buffer
    Returns per-camera aggregator state: flushed images still within their
    retention window (from MediaCache) plus the count of images currently
    sitting in the in-memory pre-flush buffer.  Presigned URLs are
    regenerated on every request so they are always valid.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.models.media_cache import MediaCache
from backend.models.sensor import Sensor

logger = get_logger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/buffer")
def get_media_buffer(
    request: Request,
    sensor_id: str | None = Query(None, description="Restrict to a single sensor ID"),
    limit: int = Query(20, ge=1, le=100, description="Max flushed images returned per sensor"),
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Return per-camera media buffer state for the admin console.

    For every enabled camera sensor the response includes:

    * **images** -- non-deleted, non-expired ``MediaCache`` entries (already
      flushed to MinIO), newest first.  Presigned URLs are regenerated on
      every call.
    * **buffer_pending** -- count of images currently in the in-memory
      aggregator buffer that have *not* yet been flushed.
    * **cooldown_remaining_seconds** -- seconds until the sensor is again
      eligible to start a new batch, or ``null`` when not in cooldown.

    Query parameters
    ----------------
    sensor_id : str, optional
        Return data for a single camera only.
    limit : int (1-100, default 20)
        Maximum number of flushed images per sensor.
    """
    aggregator = getattr(request.app.state, "event_aggregator", None)
    minio_client = getattr(request.app.state, "minio_client", None)
    now_utc = datetime.now(UTC)
    mono_now = time.monotonic()

    # Fetch camera sensors
    q = db.query(Sensor).filter(
        Sensor.sensor_type == "camera",
        Sensor.enabled.is_(True),
    )
    if sensor_id:
        q = q.filter(Sensor.id == sensor_id)
    cameras: list[Sensor] = q.order_by(Sensor.name).all()

    result = []
    url_refresh_needed = False

    for cam in cameras:
        # -- In-memory buffer state -------------------------------------------
        buffer_pending = 0
        cooldown_remaining: float | None = None

        if aggregator is not None:
            buf = aggregator.buffers.get(cam.id, [])
            buffer_pending = len(buf)

            cooldown_until = aggregator.cooldowns.get(cam.id, 0.0)
            remaining = cooldown_until - mono_now
            if remaining > 0:
                cooldown_remaining = round(remaining, 1)

        # -- Flushed images from MediaCache -----------------------------------
        stmt = (
            select(MediaCache)
            .where(
                MediaCache.sensor_id == cam.id,
                MediaCache.deleted.is_(False),
                MediaCache.expires_at > now_utc,
            )
            .order_by(MediaCache.captured_at.desc())
            .limit(limit)
        )
        rows: list[MediaCache] = list(db.execute(stmt).scalars().all())

        images = []
        for row in rows:
            url = row.presigned_url or ""
            if minio_client is not None:
                try:
                    url = minio_client.generate_presigned_url(row.object_name)
                    row.presigned_url = url
                    url_refresh_needed = True
                except Exception:
                    logger.warning(
                        "media_buffer_presign_failed",
                        object_name=row.object_name,
                        sensor_id=cam.id,
                    )
            images.append(
                {
                    "id": row.id,
                    "url": url,
                    "object_name": row.object_name,
                    "captured_at": row.captured_at.isoformat(),
                    "expires_at": row.expires_at.isoformat(),
                }
            )

        result.append(
            {
                "sensor_id": cam.id,
                "sensor_name": cam.name,
                "room_name": cam.room.name if cam.room else None,
                "buffer_pending": buffer_pending,
                "cooldown_remaining_seconds": cooldown_remaining,
                "images": images,
            }
        )

    # Persist refreshed presigned URLs in a single commit
    if url_refresh_needed:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("media_buffer_presign_commit_error")

    return result
