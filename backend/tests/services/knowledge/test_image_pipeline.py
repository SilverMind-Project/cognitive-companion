"""Tests for ImagePipeline."""
from io import BytesIO

import pytest
from PIL import Image

from backend.services.knowledge.image_pipeline import (
    MAX_UPLOAD_BYTES,
    ImagePipeline,
)


class TestValidateUpload:
    def test_rejects_unsupported_mime_type(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)  # instance without init
        with pytest.raises(ValueError, match="Unsupported MIME"):
            pipeline.validate_upload("image/gif", b"fake")

    def test_rejects_oversize_file(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        big_data = b"x" * (MAX_UPLOAD_BYTES + 1)
        with pytest.raises(ValueError, match="exceeds maximum"):
            pipeline.validate_upload("image/jpeg", big_data)

    def test_rejects_over_pixel_image(self):
        pipeline = ImagePipeline.__new__(ImagePipeline)
        # Create a small JPEG that decodes large (trick: large PNG)
        huge = Image.new("RGB", (10000, 5000))
        buf = BytesIO()
        huge.save(buf, "JPEG")
        data = buf.getvalue()
        if len(data) <= MAX_UPLOAD_BYTES:
            with pytest.raises(ValueError, match="exceed maximum"):
                pipeline.validate_upload("image/jpeg", data)

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
