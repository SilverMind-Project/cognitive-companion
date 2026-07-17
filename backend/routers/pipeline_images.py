"""Router for pipeline image source sample loading.

Provides sample images for the crop builder UI so caregivers can
draw regions against a representative frame before saving the config.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from PIL import Image

from backend.core.auth import require_permission
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.models.media_cache import MediaCache
from backend.schemas.misc_responses import SampleImageOut

router = APIRouter(prefix="/pipeline/image-sources", tags=["pipeline-images"])

logger = get_logger(__name__)

_SAMPLE_EXPIRY_MINUTES = 5


@router.get(
    "/sample",
    dependencies=[Depends(require_permission("rules:read"))],
    response_model=SampleImageOut,
)
async def get_sample_image(
    request: Request,
    source_type: str = Query(..., pattern="^(recamera|cts)$"),
    sensor_id: str | None = Query(None),
    camera_id: str | None = Query(None),
    room_name: str | None = Query(None),
):
    """Return a sample image for drawing crop regions.

    ``source_type``:
        ``recamera`` -- look up the latest MediaCache row for *sensor_id*
        ``cts`` -- capture a live snapshot from *camera_id*
    """
    minio_client = request.app.state.minio_client

    if source_type == "recamera":
        return await _recamera_sample(minio_client, sensor_id)

    if source_type == "cts":
        ingress = getattr(request.app.state, "ingress_admin_client", None)
        return await _cts_sample(minio_client, ingress, camera_id)

    raise HTTPException(status_code=400, detail=f"Unknown source_type: {source_type}")


async def _recamera_sample(minio_client, sensor_id: str | None) -> dict:
    if not sensor_id:
        raise HTTPException(
            status_code=400, detail="sensor_id is required for recamera source_type"
        )

    db = get_session()
    try:
        row = (
            db.query(MediaCache)
            .filter(
                MediaCache.sensor_id == sensor_id,
                MediaCache.deleted == False,  # noqa: E712
            )
            .order_by(MediaCache.captured_at.desc())
            .first()
        )
    finally:
        db.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"No recent image found for sensor {sensor_id}")

    presigned_url = minio_client.generate_presigned_url(row.object_name)
    width = height = None

    try:
        data = await minio_client.async_get_object(row.object_name)
        if data:
            img = Image.open(BytesIO(data))
            width, height = img.size
    except Exception:  # noqa: BLE001
        logger.warning("sample_dimensions_read_error", object_name=row.object_name)

    return {
        "image_url": presigned_url,
        "object_name": row.object_name,
        "source_type": "recamera",
        "source_id": sensor_id,
        "width": width,
        "height": height,
    }


async def _cts_sample(minio_client, ingress, camera_id: str | None) -> dict:
    if not camera_id:
        raise HTTPException(status_code=400, detail="camera_id is required for cts source_type")
    if ingress is None:
        raise HTTPException(status_code=503, detail="CTS ingress is not available")

    try:
        jpeg_bytes = await ingress.snapshot(camera_id=camera_id)
    except Exception:
        logger.exception("cts_sample_snapshot_error", camera_id=camera_id)
        raise HTTPException(
            status_code=502, detail=f"Failed to capture snapshot from camera {camera_id}"
        ) from None

    if not jpeg_bytes:
        raise HTTPException(status_code=404, detail=f"No snapshot available for camera {camera_id}")

    object_name = f"pipeline/samples/cts_{camera_id}_{uuid4().hex[:8]}.jpg"
    presigned_url = await minio_client.async_upload_bytes(jpeg_bytes, object_name, "image/jpeg")

    width = height = None
    try:
        img = Image.open(BytesIO(jpeg_bytes))
        width, height = img.size
    except Exception:  # noqa: BLE001
        pass

    db = get_session()
    try:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=_SAMPLE_EXPIRY_MINUTES)
        db.add(
            MediaCache(
                object_name=object_name,
                presigned_url=presigned_url,
                sensor_id=camera_id,
                captured_at=now,
                expires_at=expires_at,
            )
        )
        db.commit()
    except Exception:
        logger.exception("sample_media_cache_error", object_name=object_name)
        db.rollback()
    finally:
        db.close()

    return {
        "image_url": presigned_url,
        "object_name": object_name,
        "source_type": "cts",
        "source_id": camera_id,
        "width": width,
        "height": height,
    }
