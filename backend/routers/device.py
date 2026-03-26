"""
Device endpoints for hardware integrations (reCamera, reTerminal).

reCamera pushes base64-encoded images; the device key or unique ID
serves as the API key (passed in query param or JSON body since these
devices cannot set HTTP headers).
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/device", tags=["device"])


class ReCameraPayload(BaseModel):
    image: str  # base64-encoded image
    device_key: str | None = None
    sensor_id: str | None = None


class ReTerminalPayload(BaseModel):
    device_key: str
    event_type: str
    data: dict = {}


@router.post("/recamera")
async def recamera_upload(
    payload: ReCameraPayload,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("device:recamera")),
):
    """Accept a base64-encoded image from a reCamera device."""
    image_bytes = base64.b64decode(payload.image)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    object_name = f"recamera/{ts}_{unique_id}.jpg"

    # Upload to MinIO
    minio_client = getattr(request.app.state, "minio_client", None)
    media_url = ""
    if minio_client is not None:
        media_url = minio_client.upload_bytes(
            data=image_bytes,
            object_name=object_name,
            content_type="image/jpeg",
        )

    # Resolve sensor_id from auth context or payload
    sensor_id = payload.sensor_id or auth.sensor_id or "unknown"

    # Add event to aggregator
    aggregator = getattr(request.app.state, "event_aggregator", None)
    if aggregator is not None and media_url:
        await aggregator.add_event(sensor_id=sensor_id, media_path=media_url)

    logger.info(
        "recamera_image_accepted",
        object_name=object_name,
        sensor_id=sensor_id,
    )
    return {"status": "accepted", "object_name": object_name}


@router.post("/reterminal")
async def reterminal_event(
    payload: ReTerminalPayload,
    auth: AuthContext = Depends(require_permission("device:reterminal")),
):
    """Accept an event from a reTerminal device."""
    logger.info(
        "reterminal_event_received",
        event_type=payload.event_type,
        data=payload.data,
    )
    return {"status": "accepted"}
