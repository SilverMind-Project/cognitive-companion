"""
eInk display image endpoints  per-device serving, template CRUD, rendering.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.auth import AuthContext, get_auth_context_device, require_permission
from backend.core.config import settings
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.image_state import ActiveImageState
from backend.models.image_template import ImageTemplate
from backend.routers.dependencies import get_config_minio_client
from backend.schemas.image import (
    ActiveImageStateOut,
    ImageTemplateOut,
    ImageTemplateUpdate,
    RenderPayload,
    RenderPreviewPayload,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/image", tags=["image"])

# Fonts remain on the filesystem; templates and rendered images live in MinIO.
_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"


# ---------------------------------------------------------------------------
# Active image serving (per-device)
# ---------------------------------------------------------------------------


def _serve_image_for_sensor(
    sensor_id: str,
    db: Session,
    request: Request,
    minio: MinioClient,
) -> Response:
    """Serve the active image for a sensor, suppressing refresh when unchanged.

    Returns 204 No Content when the image hash matches what was last delivered
    to this device and the forced-refresh window has not yet elapsed, so the
    e-ink display can skip its pixel-refresh cycle.
    """
    eink_renderer = request.app.state.eink_renderer
    refresh_window_minutes: int = settings.as_int("image.refresh_window_minutes")
    default_template: str = settings.as_str("image.default_template", allow_empty=False)

    state = db.execute(
        select(ActiveImageState).where(ActiveImageState.sensor_id == sensor_id)
    ).scalar_one_or_none()

    now = datetime.now(UTC)

    # --- Determine which image bytes to serve ---
    if state and state.expires_at and state.expires_at < now:
        # Content has expired: fall back to the default template
        image_bytes = minio.get_object(eink_renderer.get_template_key(f"{default_template}.png"))
    else:
        image_bytes = minio.get_object(eink_renderer.get_active_image_key(sensor_id))
        if image_bytes is None:
            # No rendered active image yet: fall back to the default template
            image_bytes = minio.get_object(
                eink_renderer.get_template_key(f"{default_template}.png")
            )

    if image_bytes is None:
        raise NotFoundError("Image", f"active_{sensor_id}.png")

    # --- Decide whether the display actually needs a pixel refresh ---
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    if (
        state is not None
        and state.last_served_hash == content_hash
        and state.last_served_at is not None
        and (now - state.last_served_at).total_seconds() < refresh_window_minutes * 60
    ):
        logger.debug("eink_no_refresh", sensor_id=sensor_id)
        return Response(status_code=204)

    # --- Content changed or window elapsed: deliver image and record it ---
    if state is None:
        state = ActiveImageState(sensor_id=sensor_id)
        db.add(state)
    state.last_served_hash = content_hash
    state.last_served_at = now
    db.commit()

    logger.debug("eink_refresh", sensor_id=sensor_id, hash=content_hash[:8])
    return Response(content=image_bytes, media_type="image/png")


@router.get("/active")
def serve_active_image(
    request: Request,
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    auth: AuthContext = Depends(
        require_permission("image:read", resolver=get_auth_context_device)
    ),
):
    """Serve the active image for the authenticated device.

    Device surface: ``image:read`` is held only by reTerminal e-ink device
    keys, whose firmware is out of tree and may send the key by query string.
    Uses the permissive resolver for that reason -- no browser client calls
    this endpoint.
    """
    sensor_id = auth.sensor_id
    if not sensor_id:
        eink_renderer = request.app.state.eink_renderer
        default_template: str = settings.as_str("image.default_template", allow_empty=False)
        default_bytes = minio.get_object(eink_renderer.get_template_key(f"{default_template}.png"))
        if default_bytes is None:
            raise NotFoundError("Image", "no sensor_id in auth context")
        return Response(content=default_bytes, media_type="image/png")

    return _serve_image_for_sensor(sensor_id, db, request, minio)


# ---------------------------------------------------------------------------
# Render / Reset / Preview
# ---------------------------------------------------------------------------


@router.post("/render")
async def render_image(
    payload: RenderPayload,
    request: Request,
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Render text onto a template and set as active image for target device(s)."""
    eink_renderer = request.app.state.eink_renderer
    rendered_ids = await eink_renderer.render(
        text=payload.text,
        template=payload.template,
        template_id=payload.template_id,
        sensor_ids=payload.sensor_ids,
        expires_in_minutes=payload.expires_in_minutes,
    )
    return {"status": "rendered", "sensor_ids": rendered_ids}


@router.post("/reset")
async def reset_image(
    request: Request,
    sensor_ids: list[str] | None = None,
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Reset active images to default template for given sensors (or all)."""
    eink_renderer = request.app.state.eink_renderer
    reset_ids = await eink_renderer.reset(sensor_ids=sensor_ids)
    return {"status": "reset", "sensor_ids": reset_ids}


@router.post("/preview")
def preview_render(
    payload: RenderPreviewPayload,
    request: Request,
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Preview a rendered image without saving. Returns PNG."""
    eink_renderer = request.app.state.eink_renderer
    png_bytes = eink_renderer.render_preview(
        text=payload.text,
        template_id=payload.template_id,
        template_name=payload.template_name,
        region_name=payload.region_name,
    )
    return Response(content=png_bytes, media_type="image/png")


@router.post("/preview-form")
async def preview_render_form(
    request: Request,
    text: str = Form(...),
    regions_json: str = Form("[]"),
    font_filename: str = Form("NotoSansTamil-Regular.ttf"),
    template_id: int | None = Form(None),
    image: UploadFile | None = File(None),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Preview rendered image using an uploaded image or an existing template.

    - If ``image`` is provided, it is used as the background.
    - If only ``template_id`` is provided, the stored template image is used but
      regions/font from the form override the saved values.
    - Falls back to the default template when neither is supplied.

    Always returns PNG.
    """
    eink_renderer = request.app.state.eink_renderer
    regions: list[dict] = json.loads(regions_json)

    if image is not None:
        content = await image.read()
        png_bytes = eink_renderer.render_preview_inline(
            text=text,
            image_bytes=content,
            regions=regions,
            font_filename=font_filename,
        )
    elif template_id is not None:
        png_bytes = eink_renderer.render_preview_with_overrides(
            text=text,
            template_id=template_id,
            regions_override=regions if regions else None,
            font_filename_override=font_filename,
        )
    else:
        png_bytes = eink_renderer.render_preview(text=text)

    return Response(content=png_bytes, media_type="image/png")


# ---------------------------------------------------------------------------
# Active image states (admin)
# ---------------------------------------------------------------------------


@router.get("/states", response_model=list[ActiveImageStateOut])
def list_image_states(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """List all active image states across devices."""
    return db.execute(select(ActiveImageState)).scalars().all()


# ---------------------------------------------------------------------------
# Template CRUD
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[ImageTemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("image:read")),
):
    """List all image templates."""
    return db.execute(select(ImageTemplate).order_by(ImageTemplate.name)).scalars().all()


@router.post("/templates", response_model=ImageTemplateOut, status_code=201)
async def create_template(
    name: str = Form(...),
    description: str | None = Form(None),
    font_filename: str = Form("NotoSansTamil-Regular.ttf"),
    regions_json: str = Form("[]"),
    is_default: bool = Form(False),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Upload a new image template with bounding box regions.

    Image is resized to 800x480, converted to PNG, and stored in MinIO.
    """
    content = await image.read()
    img = Image.open(BytesIO(content))
    img = img.resize((800, 480), Image.Resampling.LANCZOS)  # type: ignore[assignment]
    img = img.convert("RGB")  # type: ignore[assignment]

    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").lower()
    filename = f"{safe_name}.png"

    buf = BytesIO()
    img.save(buf, "PNG")  # type: ignore[union-attr]
    await minio.async_upload_bytes(buf.getvalue(), f"eink/templates/{filename}", "image/png")

    regions = json.loads(regions_json)

    tmpl = ImageTemplate(
        name=name,
        description=description,
        width=800,
        height=480,
        image_filename=filename,
        font_filename=font_filename,
        regions_json=regions,
        is_default=is_default,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.put("/templates/{template_id}", response_model=ImageTemplateOut)
def update_template(
    template_id: int,
    payload: ImageTemplateUpdate,
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Update template metadata/regions (not the image file)."""
    tmpl = db.execute(
        select(ImageTemplate).where(ImageTemplate.id == template_id)
    ).scalar_one_or_none()
    if not tmpl:
        raise NotFoundError("ImageTemplate", str(template_id))

    updates = payload.model_dump(exclude_unset=True)
    if "regions_json" in updates and updates["regions_json"] is not None:
        updates["regions_json"] = [
            r.model_dump() if hasattr(r, "model_dump") else r for r in updates["regions_json"]
        ]
    for key, value in updates.items():
        setattr(tmpl, key, value)

    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.put("/templates/{template_id}/image")
async def update_template_image(
    template_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Replace the template background image. Resizes to template dimensions."""
    tmpl = db.execute(
        select(ImageTemplate).where(ImageTemplate.id == template_id)
    ).scalar_one_or_none()
    if not tmpl:
        raise NotFoundError("ImageTemplate", str(template_id))

    content = await image.read()
    img = Image.open(BytesIO(content))
    img = img.resize((tmpl.width, tmpl.height), Image.Resampling.LANCZOS)  # type: ignore[assignment]
    img = img.convert("RGB")  # type: ignore[assignment]

    buf = BytesIO()
    img.save(buf, "PNG")  # type: ignore[union-attr]
    await minio.async_upload_bytes(
        buf.getvalue(), f"eink/templates/{tmpl.image_filename}", "image/png"
    )

    return {"status": "updated", "template_id": template_id}


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """Delete a template and its image from MinIO."""
    tmpl = db.execute(
        select(ImageTemplate).where(ImageTemplate.id == template_id)
    ).scalar_one_or_none()
    if not tmpl:
        raise NotFoundError("ImageTemplate", str(template_id))

    minio.delete_object(f"eink/templates/{tmpl.image_filename}")

    db.delete(tmpl)
    db.commit()


@router.get("/templates/{template_id}/preview")
def preview_template(
    template_id: int,
    db: Session = Depends(get_db),
    minio: MinioClient = Depends(get_config_minio_client),
    _auth: AuthContext = Depends(require_permission("image:read")),
):
    """Serve the raw template image (no text rendered)."""
    tmpl = db.execute(
        select(ImageTemplate).where(ImageTemplate.id == template_id)
    ).scalar_one_or_none()
    if not tmpl:
        raise NotFoundError("ImageTemplate", str(template_id))

    image_bytes = minio.get_object(f"eink/templates/{tmpl.image_filename}")
    if image_bytes is None:
        raise NotFoundError("Image", tmpl.image_filename)

    return Response(content=image_bytes, media_type="image/png")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------


@router.get("/fonts")
def list_fonts(
    _auth: AuthContext = Depends(require_permission("admin")),
):
    """List available font files."""
    if not _FONTS_DIR.exists():
        return {"fonts": []}
    fonts = [f.name for f in _FONTS_DIR.iterdir() if f.suffix in (".ttf", ".otf")]
    return {"fonts": sorted(fonts)}
