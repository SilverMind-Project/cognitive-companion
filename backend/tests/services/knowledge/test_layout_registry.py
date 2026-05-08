"""Tests for LayoutRegistry."""
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from backend.services.knowledge.layout_registry import (
    LayoutRegistry,
)


class TestLayoutRegistry:
    def test_loads_valid_layouts(self):
        """All 5 layouts from the shipped YAML parse without errors."""
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        assert len(reg.all_layouts()) == 5
        assert reg.get("text_only") is not None
        assert reg.get("single_hero") is not None
        assert reg.get("side_by_side") is not None
        assert reg.get("gallery_grid_2x2") is not None
        assert reg.get("quiz_with_optional_image") is not None

    def test_get_for_filters_by_applies_to(self):
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        info_layouts = reg.get_for("info_card")
        assert len(info_layouts) == 4
        quiz_layouts = reg.get_for("quiz_question")
        assert len(quiz_layouts) == 1

    def test_unknown_layout_returns_none(self):
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        assert reg.get("nonexistent") is None

    def test_get_required_raises_keyerror(self):
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        with pytest.raises(KeyError):
            reg.get_required("nonexistent")

    def test_slot_specs_have_variants(self):
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        hero = reg.get_required("single_hero")
        assert len(hero.image_slots) == 1
        slot = hero.image_slots[0]
        assert slot.slot_id == "hero"
        assert "pwa" in slot.variants
        assert "eink" in slot.variants
        assert slot.variants["pwa"].target_width == 1280
        assert slot.variants["eink"].target_width == 800

    def test_text_only_has_no_slots(self):
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        text_only = reg.get_required("text_only")
        assert text_only.min_images == 0
        assert text_only.max_images == 0
        assert len(text_only.image_slots) == 0

    def test_rejects_duplicate_id(self):
        data = {"layouts": [{"id": "dup", "applies_to": ["info_card"]}, {"id": "dup", "applies_to": ["info_card"]}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            with pytest.raises(ValueError, match="Duplicate"):
                LayoutRegistry.load(f.name)
            Path(f.name).unlink()

    def test_rejects_bad_fit_mode(self):
        data = {"layouts": [{"id": "test", "applies_to": ["info_card"], "surfaces": ["pwa"], "image_slots": [{"slot_id": "s", "variants": {"pwa": {"target_width": 100, "target_height": 100, "fit_mode": "bad", "color_mode": "rgb", "format": "webp"}}}]}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            with pytest.raises(ValueError, match="fit_mode"):
                LayoutRegistry.load(f.name)
            Path(f.name).unlink()

    def test_layoutspec_is_frozen(self):
        reg = LayoutRegistry.load("config/knowledge_layouts.yaml")
        layout = reg.get_required("text_only")
        with pytest.raises(FrozenInstanceError):
            layout.display_name = "changed"
