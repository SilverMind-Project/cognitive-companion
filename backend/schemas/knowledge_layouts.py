"""Knowledge layout registry response schemas.

Layouts are operator-authored YAML loaded by LayoutRegistry, not DB rows, so these describe the
registry's in-memory objects.
"""

from __future__ import annotations

from backend.schemas.common import OutSchema


class LayoutVariantOut(OutSchema):
    """One rendering target (surface) for an image slot."""

    target_width: int
    target_height: int
    fit_mode: str
    color_mode: str
    format: str
    # None for formats that have no quality setting (e.g. the eink surface's PNG variants).
    quality: int | None = None


class LayoutSlotOut(OutSchema):
    slot_id: str
    variants: dict[str, LayoutVariantOut] = {}


class LayoutOut(OutSchema):
    id: str
    display_name: str
    applies_to: list[str] = []
    surfaces: list[str] = []
    min_images: int
    max_images: int
    image_slots: list[LayoutSlotOut] = []


class LayoutListResponse(OutSchema):
    layouts: list[LayoutOut] = []


class VoiceDefaultsOut(OutSchema):
    """Default voice instructions per delivery type."""

    interactive_prompt_default: str
    info_card_default: str
    quiz_default: str
