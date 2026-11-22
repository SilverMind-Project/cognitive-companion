"""REST API for knowledge layouts (read-only, from in-memory registry)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.core.auth import require_permission
from backend.core.exceptions import NotFoundError
from backend.routers.dependencies import get_layout_registry, get_voice_instructions
from backend.schemas.knowledge_layouts import LayoutListResponse, LayoutOut, VoiceDefaultsOut
from backend.services.knowledge.layout_registry import LayoutRegistry
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

router = APIRouter(prefix="/knowledge/layouts", tags=["knowledge-layouts"])

voice_defaults_router = APIRouter(prefix="/knowledge", tags=["knowledge-layouts"])


def _variant_out(v: Any) -> dict[str, Any]:
    return {
        "target_width": v.target_width,
        "target_height": v.target_height,
        "fit_mode": v.fit_mode,
        "color_mode": v.color_mode,
        "format": v.format,
        "quality": v.quality,
    }


def _slot_out(s: Any) -> dict[str, Any]:
    return {
        "slot_id": s.slot_id,
        "variants": {surface: _variant_out(v) for surface, v in s.variants.items()},
    }


def _layout_out(lo: Any) -> dict[str, Any]:
    return {
        "id": lo.id,
        "display_name": lo.display_name,
        "applies_to": list(lo.applies_to),
        "surfaces": list(lo.surfaces),
        "min_images": lo.min_images,
        "max_images": lo.max_images,
        "image_slots": [_slot_out(s) for s in lo.image_slots],
    }


@router.get("", response_model=LayoutListResponse)
async def list_layouts(
    applies_to: str | None = None,
    registry: LayoutRegistry = Depends(get_layout_registry),
    _auth: None = Depends(require_permission("knowledge.layouts:read")),
) -> dict[str, Any]:
    layouts = registry.get_for(applies_to) if applies_to else registry.all_layouts()
    return {"layouts": [_layout_out(lo) for lo in layouts]}


@router.get("/{layout_id}", response_model=LayoutOut)
async def get_layout(
    layout_id: str,
    registry: LayoutRegistry = Depends(get_layout_registry),
    _auth: None = Depends(require_permission("knowledge.layouts:read")),
) -> dict[str, Any]:
    layout = registry.get(layout_id)
    if layout is None:
        raise NotFoundError("Layout", layout_id)
    return _layout_out(layout)


@voice_defaults_router.get("/voice-defaults", response_model=VoiceDefaultsOut)
async def get_voice_defaults(
    vc: VoiceInstructionConfig = Depends(get_voice_instructions),
    _auth: None = Depends(require_permission("knowledge.layouts:read")),
) -> dict[str, str]:
    """Return the default voice instructions for each delivery type."""
    return {
        "interactive_prompt_default": vc.interactive_prompt_default,
        "info_card_default": vc.info_card_default,
        "quiz_default": vc.quiz_default,
    }
