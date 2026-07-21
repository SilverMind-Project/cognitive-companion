"""Extracts crops from keyframe images and submits them to the tracking-orchestrator gallery.

Supports the bbox-tagging flow: when a caregiver assigns an identity to a bounding
box, this service crops the keyframe image (using the override bbox if present, else the
YOLO-detected bbox) and POSTs the crop bytes to the orchestrator for ReID embedding and
gallery storage.
"""

from __future__ import annotations

import cv2
import numpy as np

from backend.core.logging import get_logger
from backend.core.upstream_errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from backend.integrations.minio_client import MinioClient
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.schemas.cts_bbox import BboxAnnotationResponse

logger = get_logger(__name__)


def _crop_image_bytes(image_bytes: bytes, x1: int, y1: int, x2: int, y2: int) -> bytes:
    """Decode JPEG bytes, crop to the given bbox, and re-encode as JPEG."""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode keyframe image bytes")
    h, w = img.shape[:2]
    x1 = max(0, min(x1, w - 1))
    y1 = max(0, min(y1, h - 1))
    x2 = max(x1 + 1, min(x2, w))
    y2 = max(y1 + 1, min(y2, h))
    crop = img[y1:y2, x1:x2]
    _, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return encoded.tobytes()


class GalleryUpdateService:
    """Extracts crops from keyframe images and submits them to the tracking-orchestrator gallery."""

    def __init__(
        self,
        minio_client: MinioClient,
        orchestrator_client: OrchestratorClient,
    ) -> None:
        self._minio = minio_client
        self._orchestrator_client = orchestrator_client

    async def submit_crop_for_identity(
        self,
        keyframe_object_key: str,
        bbox: BboxAnnotationResponse,
        identity_id: str,
    ) -> None:
        """Crop the keyframe image and submit it to the tracking-orchestrator gallery.

        Uses the override bbox coordinates if present; otherwise falls back to the YOLO
        detection bbox.
        """
        image_bytes = self._minio.get_object(keyframe_object_key)
        if image_bytes is None:
            logger.warning(
                "gallery_crop_missing_keyframe",
                object_key=keyframe_object_key,
                annotation_id=bbox.id,
            )
            return

        x1 = int(bbox.override_x1 if bbox.override_x1 is not None else bbox.x1)
        y1 = int(bbox.override_y1 if bbox.override_y1 is not None else bbox.y1)
        x2 = int(bbox.override_x2 if bbox.override_x2 is not None else bbox.x2)
        y2 = int(bbox.override_y2 if bbox.override_y2 is not None else bbox.y2)

        try:
            crop_bytes = _crop_image_bytes(image_bytes, x1, y1, x2, y2)
        except ValueError:
            logger.exception(
                "gallery_crop_decode_error",
                object_key=keyframe_object_key,
            )
            return

        try:
            await self._orchestrator_client.add_gallery_crop(
                payload={"crop_bytes": crop_bytes, "identity_id": identity_id}
            )
        except UpstreamError, UpstreamTimeout, UpstreamUnavailable:
            logger.exception(
                "gallery_crop_submit_error",
                annotation_id=bbox.id,
                identity_id=identity_id,
            )
            return

        logger.info(
            "gallery_crop_submitted",
            annotation_id=bbox.id,
            identity_id=identity_id,
        )
