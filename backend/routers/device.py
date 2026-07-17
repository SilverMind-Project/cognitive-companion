"""
Device endpoints for hardware integrations (reCamera).

reCamera pushes a JSON payload with a nested data object containing a
base64-encoded JPEG and the results of its on-device YOLO11 model.  The
device key (API key) is passed as the ?api_key= query parameter since these
devices cannot set HTTP headers.

Per-camera options are read from the ``cameras`` section of settings.yaml,
keyed by sensor_id:

    cameras:
      recamera_kitchen:
        rotate: 90           # optional  CW degrees: 90, 180, 270
        label_filter:
          labels: ["person"] # required label strings
          mode: "any"        # "any" (default) or "all"
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Request
from PIL import Image
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, get_auth_context_device, require_permission
from backend.core.config import settings
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.schemas.device import ReCameraPayload
from backend.schemas.misc_responses import RecameraUploadOut
from backend.services.event_aggregator import EventAggregator

logger = get_logger(__name__)

router = APIRouter(prefix="/device", tags=["device"])

# ---------------------------------------------------------------------------
# Image processing helpers
# ---------------------------------------------------------------------------


def _rotate_image_bytes(image_bytes: bytes, degrees: int) -> bytes:
    """Rotate a JPEG image clockwise by *degrees* (90, 180, or 270)."""
    if degrees not in (90, 180, 270):
        return image_bytes
    img = Image.open(BytesIO(image_bytes))
    # PIL.Image.rotate is counter-clockwise; negate for clockwise rotation.
    rotated = img.rotate(-degrees, expand=True)
    buf = BytesIO()
    rotated.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _passes_label_filter(detected_labels: list[str], filter_config: dict) -> bool:
    """Return True when *detected_labels* satisfies the label filter.

    filter_config keys:
      labels: list[str]   the required label strings
      mode:   "any"       at least one must be present (default)
              "all"       every label must be present
    """
    required = [label.strip().casefold() for label in filter_config.get("labels", [])]
    if not required:
        return True
    mode = filter_config.get("mode", "any")
    detected = {label.strip().casefold() for label in detected_labels}
    if mode == "all":
        return all(label in detected for label in required)
    return any(label in detected for label in required)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/recamera", response_model=RecameraUploadOut)
async def recamera_upload(
    payload: ReCameraPayload,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(
        require_permission("device:recamera", resolver=get_auth_context_device)
    ),
):
    """Accept a YOLO-annotated image payload from a reCamera device."""
    sensor_id = auth.sensor_id or "unknown"

    # -- Label filter ---------------------------------------------------------
    cam_config = settings.as_dict("cameras").get(sensor_id, {})
    label_filter_config: dict | None = cam_config.get("label_filter")
    detected_labels = payload.data.labels

    if label_filter_config and not _passes_label_filter(detected_labels, label_filter_config):
        logger.info(
            "recamera_image_filtered",
            sensor_id=sensor_id,
            detected_labels=detected_labels,
            required_labels=label_filter_config.get("labels"),
            mode=label_filter_config.get("mode", "any"),
        )
        return {"status": "filtered", "reason": "label_filter"}

    # -- Decode and optionally rotate ----------------------------------------
    image_bytes = base64.b64decode(payload.data.image)

    rotate_degrees: int = cam_config.get("rotate", 0)
    if rotate_degrees:
        image_bytes = _rotate_image_bytes(image_bytes, rotate_degrees)

    # -- Upload to MinIO ------------------------------------------------------
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    object_name = f"recamera/{ts}_{unique_id}.jpg"

    minio_client: MinioClient | None = request.app.state.minio_client
    media_url = ""
    if minio_client is not None:
        try:
            media_url = await minio_client.async_upload_bytes(
                data=image_bytes,
                object_name=object_name,
                content_type="image/jpeg",
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "recamera_minio_upload_failed",
                object_name=object_name,
                sensor_id=sensor_id,
                exc_info=True,
            )

    # -- Add event to aggregator ----------------------------------------------
    aggregator: EventAggregator | None = request.app.state.event_aggregator
    if aggregator is not None and media_url:
        await aggregator.add_event(sensor_id=sensor_id, media_path=media_url)

    logger.info(
        "recamera_image_accepted",
        object_name=object_name,
        sensor_id=sensor_id,
        rotate=rotate_degrees,
        detected_labels=detected_labels,
    )
    return {"status": "accepted", "object_name": object_name}
