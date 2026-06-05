"""Household-level settings API.

Provides a singleton floor-plan configuration resource plus a presigned-URL
endpoint so the frontend can upload and display the floor plan image via MinIO.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, require_permission
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.household_settings import HouseholdSettings
from backend.routers.dependencies import get_config_minio_client

router = APIRouter(prefix="/household", tags=["household"])
logger = get_logger(__name__)

_FLOOR_PLAN_PREFIX = "household/floor-plan"
MAX_FLOOR_PLAN_BYTES = 10 * 1024 * 1024  # 10 MiB

ALLOWED_EXTS: frozenset[str] = frozenset({"jpg", "jpeg", "png", "webp"})
_EXT_TO_CT: dict[str, str] = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class FloorPlanOut(BaseModel):
    floor_plan_url: str | None
    floor_plan_width: int | None
    floor_plan_height: int | None
    floor_meters_per_pixel: float | None
    updated_at: datetime | None


def _get_settings(db: Session) -> HouseholdSettings | None:
    return db.get(HouseholdSettings, 1)


def _get_or_create_settings(db: Session) -> HouseholdSettings:
    """Used by POST only. Race-safe via SAVEPOINT + retry."""
    row = db.get(HouseholdSettings, 1)
    if row is not None:
        return row
    row = HouseholdSettings(id=1)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        row = db.get(HouseholdSettings, 1)
        if row is None:
            raise
    return row


def _presign(minio: MinioClient, key: str | None) -> str | None:
    if not key:
        return None
    try:
        return minio.generate_presigned_url(key, expiration=3600)
    except Exception:  # noqa: BLE001
        logger.warning("floor_plan_presign_failed", key=key)
        return None


def _sniff_image(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.get("/floor-plan", response_model=FloorPlanOut)
async def get_floor_plan(
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("household:read")),
) -> Any:
    row = _get_settings(db)
    if row is None:
        return FloorPlanOut(
            floor_plan_url=None,
            floor_plan_width=None,
            floor_plan_height=None,
            floor_meters_per_pixel=None,
            updated_at=None,
        )
    return FloorPlanOut(
        floor_plan_url=_presign(minio, row.floor_plan_key),
        floor_plan_width=row.floor_plan_width,
        floor_plan_height=row.floor_plan_height,
        floor_meters_per_pixel=row.floor_meters_per_pixel,
        updated_at=row.updated_at,
    )


@router.post("/floor-plan", response_model=FloorPlanOut)
async def post_floor_plan(
    file: UploadFile | None = File(None),
    floor_plan_width: int | None = Form(None),
    floor_plan_height: int | None = Form(None),
    floor_meters_per_pixel: float | None = Form(None),
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("household:write")),
) -> Any:
    row = _get_or_create_settings(db)

    if file is not None:
        raw_name = (file.filename or "").lower()
        ext = raw_name.rsplit(".", 1)[-1] if "." in raw_name else ""
        if ext not in ALLOWED_EXTS:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported floor-plan file type {ext!r}; allowed: {sorted(ALLOWED_EXTS)}",
            )

        buf = bytearray()
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > MAX_FLOOR_PLAN_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Floor-plan file exceeds {MAX_FLOOR_PLAN_BYTES} bytes",
                )
        data = bytes(buf)

        content_type = _EXT_TO_CT[ext]
        sniffed = _sniff_image(data)
        if sniffed is not None and sniffed != content_type:
            raise HTTPException(
                status_code=415,
                detail="File contents do not match declared image type",
            )

        key = f"{_FLOOR_PLAN_PREFIX}/{uuid.uuid4().hex}.{ext}"
        await minio.async_upload_bytes(data, key, content_type)
        row.floor_plan_key = key
        logger.info("floor_plan_uploaded", key=key, size=len(data))

    if floor_plan_width is not None:
        row.floor_plan_width = floor_plan_width
    if floor_plan_height is not None:
        row.floor_plan_height = floor_plan_height
    if floor_meters_per_pixel is not None:
        row.floor_meters_per_pixel = floor_meters_per_pixel

    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)

    return FloorPlanOut(
        floor_plan_url=_presign(minio, row.floor_plan_key),
        floor_plan_width=row.floor_plan_width,
        floor_plan_height=row.floor_plan_height,
        floor_meters_per_pixel=row.floor_meters_per_pixel,
        updated_at=row.updated_at,
    )
