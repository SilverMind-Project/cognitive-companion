"""Pydantic schemas for e-ink image template and rendering endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from backend.schemas.common import OptionalUTCDatetime, UTCDatetime


class TextRegion(BaseModel):
    name: str = "main_text"
    x: int
    y: int
    width: int
    height: int
    font_size_max: int = 48
    font_size_min: int = 12
    align: str = "center"
    bg_color: list[int] = [0, 0, 0, 160]
    text_color: list[int] = [255, 255, 255, 255]


class ImageTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    width: int = 800
    height: int = 480
    font_filename: str = "NotoSansTamil-Regular.ttf"
    regions_json: list[TextRegion] = []
    is_default: bool = False


class ImageTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    width: int | None = None
    height: int | None = None
    font_filename: str | None = None
    regions_json: list[TextRegion] | None = None
    is_default: bool | None = None


class ImageTemplateOut(BaseModel):
    id: int
    name: str
    description: str | None
    width: int
    height: int
    image_filename: str
    font_filename: str
    regions_json: list[dict]
    is_default: bool
    created_at: UTCDatetime
    updated_at: OptionalUTCDatetime

    model_config = {"from_attributes": True}


class RenderPayload(BaseModel):
    text: str
    template: str | None = "alert"
    template_id: int | None = None
    sensor_ids: list[str] | None = None
    expires_in_minutes: int = 30


class RenderPreviewPayload(BaseModel):
    text: str
    template_id: int | None = None
    template_name: str | None = "alert"
    region_name: str | None = None


class ActiveImageStateOut(BaseModel):
    id: int
    sensor_id: str
    template_id: int | None
    rendered_text: str | None
    expires_at: OptionalUTCDatetime
    updated_at: OptionalUTCDatetime

    model_config = {"from_attributes": True}
