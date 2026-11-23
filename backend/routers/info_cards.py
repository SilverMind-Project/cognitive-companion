"""REST API for info cards and image slots.
Thin router: parse, call service, serialize.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from backend.core.auth import AuthContext, actor_from_auth, require_permission
from backend.core.exceptions import ValidationError
from backend.routers.dependencies import get_content_generation, get_info_card_service
from backend.schemas.info_cards import (
    InfoCardCreate,
    InfoCardListResponse,
    InfoCardOut,
    InfoCardSlotPatch,
    InfoCardSlotResponse,
    InfoCardStatusOut,
    InfoCardSuggestionOut,
    InfoCardUpdate,
)
from backend.services.knowledge.content_generation import ContentGenerationService
from backend.services.knowledge.info_card_service import InfoCardService

router = APIRouter(prefix="/info-cards", tags=["info-cards"])


# -- CRUD --------------------------------------------------------------------


@router.post("", status_code=201, response_model=InfoCardOut)
async def create_info_card(
    body: InfoCardCreate,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, Any]:
    return svc.create_card(
        title=body.title,
        body_text=body.body_text,
        layout_id=body.layout_id,
        document_id=body.document_id,
        voice_instruction=body.voice_instruction,
        tags=body.tags,
    )


@router.get("", response_model=InfoCardListResponse)
async def list_info_cards(
    status: str | None = Query(None),
    tag: list[str] | None = Query(
        None, description="Matches items carrying any of these tags (repeat the parameter)."
    ),
    document_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:read")),
) -> dict[str, Any]:
    return svc.list_cards(
        status=status,
        tags=tag,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{card_id}", response_model=InfoCardOut)
async def get_info_card(
    card_id: int,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:read")),
) -> dict[str, Any]:
    return svc.get_card(card_id)


@router.patch("/{card_id}", response_model=InfoCardOut)
async def update_info_card(
    card_id: int,
    body: InfoCardUpdate,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, Any]:
    return await svc.update_card(card_id, updates=body.model_dump(exclude_none=True))


# -- state transitions -------------------------------------------------------


@router.post("/{card_id}/approve", response_model=InfoCardOut)
async def approve_info_card(
    card_id: int,
    svc: InfoCardService = Depends(get_info_card_service),
    auth: AuthContext = Depends(require_permission("info_cards:write")),
) -> dict[str, Any]:
    return svc.approve_card(card_id, approved_by=actor_from_auth(auth))


@router.post("/{card_id}/archive", response_model=InfoCardStatusOut)
async def archive_info_card(
    card_id: int,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, str]:
    return svc.archive_card(card_id)


@router.post("/{card_id}/restore", response_model=InfoCardStatusOut)
async def restore_info_card(
    card_id: int,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, str]:
    return svc.restore_card(card_id)


@router.delete("/{card_id}", status_code=204)
async def delete_info_card(
    card_id: int,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:delete")),
) -> None:
    await svc.delete_card(card_id)


@router.post("/suggest", response_model=InfoCardSuggestionOut)
async def suggest_info_card(
    document_id: int | None = None,
    model_id: str | None = None,
    content_gen: ContentGenerationService = Depends(get_content_generation),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, str]:
    """Generate a paraphrased info card draft via LLM."""
    if document_id is None:
        raise ValidationError("document_id is required")

    suggestion = await content_gen.suggest_paraphrase(document_id, model_id=model_id)
    return {
        "title": suggestion.title,
        "body_text": suggestion.body_text,
        "voice_instruction": suggestion.voice_instruction,
    }


# -- slots -------------------------------------------------------------------


@router.put("/{card_id}/slots/{slot_index}", response_model=InfoCardSlotResponse)
async def set_info_card_slot(
    card_id: int,
    slot_index: int,
    file: UploadFile | None = File(None),
    source_image_id: int | None = Form(None),
    alt_text: str = Form(""),
    crop_hints: str | None = Form(None),
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, Any]:
    _ = crop_hints
    file_bytes = await file.read() if file is not None else None
    content_type = file.content_type if file is not None else None
    return await svc.set_slot(
        card_id,
        slot_index,
        file_bytes=file_bytes,
        content_type=content_type,
        source_image_id=source_image_id,
        alt_text=alt_text,
    )


@router.patch("/{card_id}/slots/{slot_index}", response_model=InfoCardSlotResponse)
async def patch_info_card_slot(
    card_id: int,
    slot_index: int,
    body: InfoCardSlotPatch,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:write")),
) -> dict[str, Any]:
    return svc.patch_slot(card_id, slot_index, alt_text=body.alt_text)


@router.delete("/{card_id}/slots/{slot_index}", status_code=204)
async def delete_info_card_slot(
    card_id: int,
    slot_index: int,
    svc: InfoCardService = Depends(get_info_card_service),
    _auth: None = Depends(require_permission("info_cards:delete")),
) -> None:
    await svc.delete_slot(card_id, slot_index)
