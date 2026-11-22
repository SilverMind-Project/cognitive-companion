"""Tests for ImagePipeline."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from backend.core.exceptions import ValidationError
from backend.services.knowledge.image_pipeline import (
    MAX_UPLOAD_BYTES,
    ImagePipeline,
)


class TestValidateUpload:
    def test_rejects_unsupported_mime_type(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)  # instance without init
        with pytest.raises(ValidationError, match="Unsupported MIME"):
            pipeline.validate_upload("image/gif", b"fake")

    def test_rejects_oversize_file(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        big_data = b"x" * (MAX_UPLOAD_BYTES + 1)
        with pytest.raises(ValidationError, match="exceeds maximum"):
            pipeline.validate_upload("image/jpeg", big_data)

    def test_rejects_over_pixel_image(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        # Create a small JPEG that decodes large (trick: large PNG)
        huge = Image.new("RGB", (10000, 5000))
        buf = BytesIO()
        huge.save(buf, "JPEG")
        data = buf.getvalue()
        if len(data) <= MAX_UPLOAD_BYTES:
            with pytest.raises(ValidationError, match="exceed maximum"):
                pipeline.validate_upload("image/jpeg", data)

    def test_rejects_undecodable_bytes_as_validation_error(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        with pytest.raises(ValidationError, match="not a readable image"):
            pipeline.validate_upload("image/jpeg", b"definitely not a jpeg")

    def test_accepts_valid_jpeg(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        img = Image.new("RGB", (100, 100))
        buf = BytesIO()
        img.save(buf, "JPEG")
        w, h = pipeline.validate_upload("image/jpeg", buf.getvalue())
        assert w == 100
        assert h == 100

    def test_accepts_valid_png(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        img = Image.new("RGBA", (200, 150))
        buf = BytesIO()
        img.save(buf, "PNG")
        w, h = pipeline.validate_upload("image/png", buf.getvalue())
        assert (w, h) == (200, 150)


class TestRenderVariants:
    async def test_renders_every_surface_off_the_event_loop(self, monkeypatch):
        import threading
        from unittest.mock import AsyncMock, Mock

        from backend.services.knowledge.layout_registry import LayoutRegistry

        layouts = LayoutRegistry.load("config/knowledge_layouts.yaml")
        source = BytesIO()
        Image.new("RGB", (1200, 900), "white").save(source, "JPEG")
        minio = Mock()
        minio.async_get_object = AsyncMock(return_value=source.getvalue())
        minio.async_upload_bytes = AsyncMock()
        pipeline = ImagePipeline(minio_client=minio, layouts=layouts)

        loop_thread = threading.get_ident()
        encode_threads: list[int] = []
        original_encode = ImagePipeline._encode_variants

        def spy(self, *args, **kwargs):
            encode_threads.append(threading.get_ident())
            return original_encode(self, *args, **kwargs)

        monkeypatch.setattr(ImagePipeline, "_encode_variants", spy)

        variants = await pipeline.render_variants(
            original_object_name="info_cards/1/slot0__original.jpg",
            layout_id="single_hero",
            slot_id="hero",
            target_key_prefix="info_cards/1/slot0",
        )

        spec = layouts.get_required("single_hero").image_slots[0].variants
        assert set(variants) == set(spec)
        for surface, rendered in variants.items():
            assert rendered.object_name == f"info_cards/1/slot0__{surface}.{spec[surface].format}"
            assert 0 < rendered.width <= spec[surface].target_width
            assert 0 < rendered.height <= spec[surface].target_height
        assert minio.async_upload_bytes.await_count == len(spec)
        assert encode_threads
        assert loop_thread not in encode_threads
