"""Pydantic v2 wire models for info cards and image slots."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime

# -- Info Card ----------------------------------------------------------------


class InfoCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int | None = None
    layout_id: str = "text_only"
    title: str
    body_text: str
    voice_instruction: str = ""
    tags: list[str] = []


class InfoCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    body_text: str | None = None
    voice_instruction: str | None = None
    tags: list[str] | None = None
    layout_id: str | None = None


class InfoCardSlotResponse(OutSchema):
    id: int
    info_card_id: int
    slot_index: int
    source_image_id: int | None = None
    original_object_name: str
    alt_text: str = ""
    variants: dict[str, Any] = {}


class InfoCardOut(OutSchema):
    id: int
    document_id: int | None = None
    layout_id: str
    title: str
    body_text: str
    voice_instruction: str = ""
    tags: list[str] = []
    status: str
    version: int = 1
    approved_by: str | None = None
    approved_at: OptionalUTCDatetime = None
    created_at: UTCDatetime
    updated_at: UTCDatetime
    image_slots: list[InfoCardSlotResponse] = []


class InfoCardListOut(OutSchema):
    id: int
    document_id: int | None = None
    layout_id: str
    title: str
    tags: list[str] = []
    status: str
    version: int = 1
    approved_by: str | None = None
    created_at: UTCDatetime
    updated_at: UTCDatetime
    slot_count: int = 0


class InfoCardPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface: str = "pwa"


# -- Info Card Slot -----------------------------------------------------------


class InfoCardSlotUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_image_id: int | None = None
    alt_text: str | None = None
    crop_hints: dict[str, int] | None = None


class InfoCardSlotPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alt_text: str | None = None
    crop_hints: dict[str, int] | None = None
