"""REST API for info cards and image slots.
Thin router: parse, call service, serialize.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.knowledge import InfoCard, InfoCardImageSlot
from backend.schemas.info_cards import (
    InfoCardCreate,
    InfoCardPreviewRequest,
    InfoCardSlotPatch,
    InfoCardUpdate,
)

router = APIRouter(prefix="/info-cards", tags=["info-cards"])


# -- CRUD --------------------------------------------------------------------


@router.post("", status_code=201)
async def create_info_card(
    body: InfoCardCreate,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    layout_registry = request.app.state.layout_registry
    layout = layout_registry.get_required(body.layout_id)
    if "info_card" not in layout.applies_to:
        raise ValidationError(f"Layout '{body.layout_id}' does not apply to info_card")

    card = InfoCard(
        document_id=body.document_id,
        layout_id=body.layout_id,
        title=body.title,
        body_text=body.body_text,
        tags=body.tags,
        status="draft",
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return _card_out(card, request.app.state.minio_client, request.app.state.layout_registry)


@router.get("")
async def list_info_cards(
    request: Request,
    status: str | None = Query(None),
    tag: str | None = Query(None),
    document_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/info-cards")),
):
    stmt = select(InfoCard)
    count_stmt = select(func.count(InfoCard.id))
    if status:
        stmt = stmt.where(InfoCard.status == status)
        count_stmt = count_stmt.where(InfoCard.status == status)
    if tag:
        stmt = stmt.where(InfoCard.tags.contains([tag]))
        count_stmt = count_stmt.where(InfoCard.tags.contains([tag]))
    if document_id is not None:
        stmt = stmt.where(InfoCard.document_id == document_id)
        count_stmt = count_stmt.where(InfoCard.document_id == document_id)

    total = db.execute(count_stmt).scalar() or 0
    cards = db.execute(
        stmt.order_by(InfoCard.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()

    _ = request.app.state.minio_client  # ensure MinIO is available
    return {
        "items": [
            {
                "id": c.id,
                "document_id": c.document_id,
                "layout_id": c.layout_id,
                "title": c.title,
                "tags": c.tags or [],
                "status": c.status,
                "version": c.version,
                "approved_by": c.approved_by,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "slot_count": len(c.image_slots) if c.image_slots else 0,
            }
            for c in cards
        ],
        "total": total,
    }


@router.get("/{card_id}")
async def get_info_card(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)
    return _card_out(card, request.app.state.minio_client, request.app.state.layout_registry)


@router.patch("/{card_id}")
async def update_info_card(
    card_id: int,
    body: InfoCardUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("PATCH /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)

    for key, val in body.model_dump(exclude_none=True).items():
        setattr(card, key, val)

    # Layout change validation
    if body.layout_id:
        layout_registry = request.app.state.layout_registry
        layout = layout_registry.get_required(body.layout_id)
        if "info_card" not in layout.applies_to:
            raise ValidationError(f"Layout '{body.layout_id}' does not apply to info_card")

    db.commit()
    db.refresh(card)
    return _card_out(card, request.app.state.minio_client, request.app.state.layout_registry)


# -- state transitions -------------------------------------------------------


@router.post("/{card_id}/approve")
async def approve_info_card(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)

    # Validate min_images
    layout_registry = request.app.state.layout_registry
    layout = layout_registry.get_required(card.layout_id)
    if len(card.image_slots) < layout.min_images:
        raise ValidationError(
            f"Layout '{layout.id}' requires at least {layout.min_images} image(s), "
            f"got {len(card.image_slots)}"
        )

    card.status = "approved"
    card.version += 1
    from datetime import UTC, datetime
    card.approved_at = datetime.now(UTC)
    card.approved_by = getattr(request.state, "auth_context", None)
    if card.approved_by and hasattr(card.approved_by, "name"):
        card.approved_by = card.approved_by.name
    db.commit()
    db.refresh(card)
    return _card_out(card, request.app.state.minio_client, layout_registry)


@router.post("/{card_id}/archive")
async def archive_info_card(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)
    card.status = "archived"
    db.commit()
    return {"status": "archived"}


@router.post("/{card_id}/restore")
async def restore_info_card(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)
    card.status = "draft"
    db.commit()
    return {"status": "restored"}


@router.delete("/{card_id}", status_code=204)
async def delete_info_card(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("DELETE /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)
    db.delete(card)
    db.commit()
    pipeline = request.app.state.image_pipeline
    await pipeline.purge_prefix(f"info_cards/{card_id}/")


@router.post("/suggest")
async def suggest_info_card(
    request: Request,
    document_id: int | None = None,
    model_id: str | None = None,
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    """Generate a paraphrased info card draft via LLM."""
    if document_id is None:
        from backend.core.exceptions import ValidationError
        raise ValidationError("document_id is required")

    content_gen = request.app.state.knowledge_content_gen
    suggestion = await content_gen.suggest_paraphrase(document_id, model_id=model_id)
    return {
        "title": suggestion.title,
        "body_text": suggestion.body_text,
        "voice_instruction": suggestion.voice_instruction,
    }


@router.post("/{card_id}/preview")
async def preview_info_card(
    card_id: int,
    body: InfoCardPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    return {"status": "not_implemented", "message": "Preview available in Phase 3"}


# -- slots -------------------------------------------------------------------


@router.put("/{card_id}/slots/{slot_index}")
async def set_info_card_slot(
    card_id: int,
    slot_index: int,
    request: Request,
    file: UploadFile | None = File(None),
    source_image_id: int | None = Form(None),
    alt_text: str = Form(""),
    crop_hints: str | None = Form(None),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
    if card is None:
        raise NotFoundError("Info card", card_id)

    layout_registry = request.app.state.layout_registry
    layout = layout_registry.get_required(card.layout_id)
    if slot_index >= len(layout.image_slots):
        raise ValidationError(
            f"Layout '{layout.id}' has no slot at index {slot_index}"
        )

    minio = request.app.state.minio_client
    pipeline = request.app.state.image_pipeline

    original_object_name = ""
    if file:
        data = await file.read()
        content_type = file.content_type or "image/jpeg"
        pipeline.validate_upload(content_type, data)
        ext = content_type.split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        object_name = f"info_cards/{card_id}/slot{slot_index}__original.{ext}"
        minio.upload_bytes(data, object_name, content_type)
        original_object_name = object_name
    elif source_image_id is not None:
        from backend.models.knowledge import KnowledgeDocumentImage
        src = db.execute(
            select(KnowledgeDocumentImage).where(KnowledgeDocumentImage.id == source_image_id)
        ).scalar_one_or_none()
        if src is None:
            raise NotFoundError("Source image", source_image_id)
        original_object_name = src.minio_object_name

    # Upsert or create slot row
    slot = db.execute(
        select(InfoCardImageSlot).where(
            InfoCardImageSlot.info_card_id == card_id,
            InfoCardImageSlot.slot_index == slot_index,
        )
    ).scalar_one_or_none()

    if slot is None:
        slot = InfoCardImageSlot(
            info_card_id=card_id,
            slot_index=slot_index,
            source_image_id=source_image_id,
            original_object_name=original_object_name,
            alt_text=alt_text,
        )
        db.add(slot)
    else:
        if original_object_name:
            slot.original_object_name = original_object_name
        if source_image_id is not None:
            slot.source_image_id = source_image_id
        slot.alt_text = alt_text or slot.alt_text

    db.commit()
    db.refresh(slot)

    # Render variants (async for large images; sync for v1)
    if original_object_name:
        try:
            variants = await pipeline.render_variants(
                original_object_name=original_object_name,
                layout_id=card.layout_id,
                slot_id=layout.image_slots[slot_index].slot_id,
                target_key_prefix=f"info_cards/{card_id}/slot{slot_index}",
            )
            slot.variants = {
                surface: {
                    "object_name": v.object_name,
                    "width": v.width,
                    "height": v.height,
                    "format": v.format,
                    "generated_at": v.generated_at,
                }
                for surface, v in variants.items()
            }
            db.commit()
            db.refresh(slot)
        except Exception:
            pass  # variant render is best-effort

    return _slot_out(slot, minio)


@router.patch("/{card_id}/slots/{slot_index}")
async def patch_info_card_slot(
    card_id: int,
    slot_index: int,
    body: InfoCardSlotPatch,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("PATCH /api/v1/info-cards")),
):
    slot = db.execute(
        select(InfoCardImageSlot).where(
            InfoCardImageSlot.info_card_id == card_id,
            InfoCardImageSlot.slot_index == slot_index,
        )
    ).scalar_one_or_none()
    if slot is None:
        raise NotFoundError(f"Slot for info card {card_id}", slot_index)
    if body.alt_text is not None:
        slot.alt_text = body.alt_text
    db.commit()
    return _slot_out(slot, request.app.state.minio_client)


@router.delete("/{card_id}/slots/{slot_index}", status_code=204)
async def delete_info_card_slot(
    card_id: int,
    slot_index: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("DELETE /api/v1/info-cards")),
):
    slot = db.execute(
        select(InfoCardImageSlot).where(
            InfoCardImageSlot.info_card_id == card_id,
            InfoCardImageSlot.slot_index == slot_index,
        )
    ).scalar_one_or_none()
    if slot is None:
        raise NotFoundError(f"Slot for info card {card_id}", slot_index)
    db.delete(slot)
    db.commit()
    pipeline = request.app.state.image_pipeline
    await pipeline.purge_prefix(f"info_cards/{card_id}/slot{slot_index}")


@router.post("/{card_id}/rerender")
async def rerender_info_card(
    card_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/info-cards")),
):
    return {"status": "not_implemented", "message": "Batch re-render available in Phase 5"}


# -- serialisers ------------------------------------------------------------


def _card_out(card: InfoCard, minio_client, layout_registry) -> dict[str, Any]:
    return {
        "id": card.id,
        "document_id": card.document_id,
        "layout_id": card.layout_id,
        "title": card.title,
        "body_text": card.body_text,
        "voice_instruction": card.voice_instruction or "",
        "tags": card.tags or [],
        "status": card.status,
        "version": card.version,
        "approved_by": card.approved_by,
        "approved_at": card.approved_at.isoformat() if card.approved_at else None,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
        "image_slots": [_slot_out(s, minio_client) for s in (card.image_slots or [])],
    }


def _slot_out(slot, minio_client) -> dict[str, Any]:
    variants = {}
    for surface, v in (slot.variants or {}).items():
        entry = dict(v)
        object_name = v.get("object_name", "")
        if object_name and minio_client:
            try:
                entry["presigned_url"] = minio_client.generate_presigned_url(object_name)
            except Exception:
                entry["presigned_url"] = None
        else:
            entry["presigned_url"] = None
        variants[surface] = entry

    return {
        "id": slot.id,
        "info_card_id": slot.info_card_id,
        "slot_index": slot.slot_index,
        "source_image_id": slot.source_image_id,
        "original_object_name": slot.original_object_name,
        "alt_text": slot.alt_text,
        "variants": variants,
    }
