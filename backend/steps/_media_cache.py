"""Shared MediaCache row registration.

``image_crop`` and ``media_presign`` both track MinIO objects they hand out
presigned URLs for so a background sweep can expire them; this module is the
one place that upsert logic lives instead of being copied per step.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from backend.core.logging import get_logger
from backend.models.media_cache import MediaCache

if TYPE_CHECKING:
    from backend.steps.base import ServiceContainer

logger = get_logger(__name__)


def register_media_cache_row(
    services: ServiceContainer,
    object_name: str,
    presigned_url: str,
    *,
    sensor_id: str | None,
    retention_minutes: int,
) -> None:
    """Upsert one MediaCache row, idempotent on ``object_name``.

    Failures are logged and swallowed: a MediaCache row is a cleanup-tracking
    side record, not the artifact itself, so a DB hiccup here must not fail
    the step that already produced a usable presigned URL.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=retention_minutes)

    db = services.db_factory()
    try:
        row = db.query(MediaCache).filter(MediaCache.object_name == object_name).first()
        if row is None:
            row = MediaCache(
                object_name=object_name,
                presigned_url=presigned_url,
                sensor_id=sensor_id,
                captured_at=now,
                expires_at=expires_at,
            )
            db.add(row)
        else:
            row.presigned_url = presigned_url
            row.sensor_id = sensor_id
            row.expires_at = expires_at
        db.commit()
    except Exception:
        logger.exception("media_cache_register_error", object_name=object_name)
        db.rollback()
    finally:
        db.close()
