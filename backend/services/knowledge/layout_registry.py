"""Typed layout registry loaded from config/knowledge_layouts.yaml.

Validates every layout, slot, and variant spec at startup. Unknown enum
values raise immediately so a bad config crashes the process rather than
a senior-facing delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Allowed enum values
FIT_MODES = frozenset({"cover", "contain", "pad"})
COLOR_MODES = frozenset({"rgb", "grayscale", "bw_dither"})
FORMATS = frozenset({"webp", "jpeg", "png"})
APPLIES_TO_VALUES = frozenset({"info_card", "quiz_question"})
SURFACE_VALUES = frozenset({"pwa", "eink"})


@dataclass(frozen=True, slots=True)
class ImageVariantSpec:
    """Render target for one delivery surface."""

    target_width: int
    target_height: int
    fit_mode: str  # cover | contain | pad
    color_mode: str  # rgb | grayscale | bw_dither
    format: str  # webp | jpeg | png
    quality: int | None = None


@dataclass(frozen=True, slots=True)
class ImageSlotSpec:
    """One image slot in a layout, with per-surface variant targets."""

    slot_id: str
    variants: dict[str, ImageVariantSpec]


@dataclass(frozen=True, slots=True)
class LayoutSpec:
    """A complete layout definition for info cards or quiz questions."""

    id: str
    display_name: str
    applies_to: tuple[str, ...]
    surfaces: tuple[str, ...]
    min_images: int
    max_images: int
    image_slots: tuple[ImageSlotSpec, ...]


@dataclass(frozen=True, slots=True)
class LayoutRegistry:
    """In-memory registry of all layouts, loaded from YAML at startup."""

    _by_id: dict[str, LayoutSpec] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> LayoutRegistry:
        """Parse and validate the layout YAML file. Raises ValueError on bad input."""
        path = Path(path)
        if not path.is_absolute():
            # Resolve relative to the repo root (config/ is one level above backend/)
            candidate = Path.cwd().parent / path
            if candidate.exists():
                path = candidate

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries = raw.get("layouts", [])
        if not isinstance(entries, list):
            raise ValueError("knowledge_layouts.yaml: 'layouts' must be a list")

        by_id: dict[str, LayoutSpec] = {}
        for entry in entries:
            layout = cls._parse_entry(entry)
            if layout.id in by_id:
                raise ValueError(f"Duplicate layout id: {layout.id}")
            by_id[layout.id] = layout

        logger.info("layout_registry_loaded", count=len(by_id), path=str(path))
        return cls(_by_id=by_id)

    def get(self, layout_id: str) -> LayoutSpec | None:
        return self._by_id.get(layout_id)

    def get_required(self, layout_id: str) -> LayoutSpec:
        layout = self._by_id.get(layout_id)
        if layout is None:
            raise KeyError(f"Unknown layout id: {layout_id}")
        return layout

    def get_for(self, applies_to: str) -> list[LayoutSpec]:
        return [l for l in self._by_id.values() if applies_to in l.applies_to]

    def all_layouts(self) -> list[LayoutSpec]:
        return list(self._by_id.values())

    # -- internal -------------------------------------------------------

    @staticmethod
    def _parse_entry(entry: dict[str, Any]) -> LayoutSpec:
        lid = entry.get("id")
        if not isinstance(lid, str) or not lid:
            raise ValueError(f"Layout entry missing valid 'id': {entry}")

        applies_to_raw = entry.get("applies_to", [])
        if not isinstance(applies_to_raw, list):
            raise ValueError(f"Layout '{lid}': 'applies_to' must be a list")
        for v in applies_to_raw:
            if v not in APPLIES_TO_VALUES:
                raise ValueError(f"Layout '{lid}': unknown applies_to value '{v}'")

        surfaces_raw = entry.get("surfaces", [])
        if not isinstance(surfaces_raw, list):
            raise ValueError(f"Layout '{lid}': 'surfaces' must be a list")
        for s in surfaces_raw:
            if s not in SURFACE_VALUES:
                raise ValueError(f"Layout '{lid}': unknown surface '{s}'")

        slots_raw = entry.get("image_slots", [])
        slots: list[ImageSlotSpec] = []
        for slot_entry in slots_raw:
            slots.append(LayoutRegistry._parse_slot(lid, slot_entry))

        return LayoutSpec(
            id=lid,
            display_name=entry.get("display_name", lid),
            applies_to=tuple(applies_to_raw),
            surfaces=tuple(surfaces_raw),
            min_images=entry.get("min_images", 0),
            max_images=entry.get("max_images", len(slots_raw)),
            image_slots=tuple(slots),
        )

    @staticmethod
    def _parse_slot(layout_id: str, entry: dict[str, Any]) -> ImageSlotSpec:
        slot_id = entry.get("slot_id")
        if not isinstance(slot_id, str) or not slot_id:
            raise ValueError(f"Layout '{layout_id}': slot missing valid 'slot_id'")

        variants_raw = entry.get("variants", {})
        variants: dict[str, ImageVariantSpec] = {}
        for surface, v in variants_raw.items():
            if surface not in SURFACE_VALUES:
                raise ValueError(
                    f"Layout '{layout_id}' slot '{slot_id}': unknown surface '{surface}'"
                )
            variants[surface] = LayoutRegistry._parse_variant(layout_id, slot_id, surface, v)

        return ImageSlotSpec(slot_id=slot_id, variants=variants)

    @staticmethod
    def _parse_variant(
        layout_id: str, slot_id: str, surface: str, entry: dict[str, Any]
    ) -> ImageVariantSpec:
        fm = entry.get("fit_mode", "cover")
        if fm not in FIT_MODES:
            raise ValueError(
                f"Layout '{layout_id}' slot '{slot_id}' surface '{surface}': "
                f"unknown fit_mode '{fm}'"
            )
        cm = entry.get("color_mode", "rgb")
        if cm not in COLOR_MODES:
            raise ValueError(
                f"Layout '{layout_id}' slot '{slot_id}' surface '{surface}': "
                f"unknown color_mode '{cm}'"
            )
        fmt = entry.get("format", "webp")
        if fmt not in FORMATS:
            raise ValueError(
                f"Layout '{layout_id}' slot '{slot_id}' surface '{surface}': "
                f"unknown format '{fmt}'"
            )
        return ImageVariantSpec(
            target_width=entry["target_width"],
            target_height=entry["target_height"],
            fit_mode=fm,
            color_mode=cm,
            format=fmt,
            quality=entry.get("quality"),
        )
