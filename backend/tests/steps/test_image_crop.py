"""Unit tests for :class:`~backend.steps.builtin.image_crop.ImageCropHandler`.

Uses Pillow-generated in-memory images and a fake MinIO so no real
network or object storage is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.image_crop import ImageCropHandler

# ---------------------------------------------------------------------------
# Fake MinIO
# ---------------------------------------------------------------------------


class _FakeMinio:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    async def async_get_object(self, key):
        return self.objects.get(key)

    async def async_upload_bytes(self, data, object_name, content_type):
        self.objects[object_name] = data
        return f"http://minio.local/bucket/{object_name}?sig=test"

    def generate_presigned_url(self, object_name, expiration=3600):
        return f"http://minio.local/bucket/{object_name}?sig=test"

    def extract_object_name(self, presigned_url):
        return presigned_url.split("/bucket/", 1)[1].split("?", 1)[0]


# ---------------------------------------------------------------------------
# Test image factory
# ---------------------------------------------------------------------------


def _make_test_image(width: int = 200, height: int = 150) -> bytes:
    """Generate a solid-colour JPEG in memory."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)
    id: int = 1
    label: str = "crop_1"


@dataclass
class _FakeExecution:
    id: int = 100


def _make_trigger(
    sensor_id: str = "cam-1",
    media_paths: list[str] | None = None,
) -> TriggerContext:
    return TriggerContext(
        trigger_type="sensor_event",
        sensor_id=sensor_id,
        room_name="Kitchen",
        media_paths=media_paths or [],
    )


def _make_services(minio_client=None, db_factory=None) -> ServiceContainer:
    return ServiceContainer(
        db_factory=db_factory or MagicMock(),
        minio_client=minio_client,
    )


def _make_mock_db() -> MagicMock:
    """Return a mock DB session that supports query chaining for MediaCache."""
    session = MagicMock()
    session.query.return_value = session
    session.filter.return_value = session
    session.filter_by.return_value = session
    session.first.return_value = None  # No existing row
    return session


_STANDARD_REGIONS = [
    {
        "id": "stove",
        "name": "Stove area",
        "x": 0.25,
        "y": 0.25,
        "width": 0.5,
        "height": 0.5,
    }
]

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMissingServices:
    @pytest.mark.asyncio
    async def test_no_minio_returns_failure(self):
        handler = ImageCropHandler()
        result = await handler.execute(
            _FakeStep(),
            _FakeExecution(),
            {},
            _make_trigger(),
            _make_services(minio_client=None),
        )

        assert result.success is False
        assert result.data["count"] == 0
        assert "minio_unavailable" in str(result.data["skipped"])
        assert result.data.get("error")


class TestNoRegions:
    @pytest.mark.asyncio
    async def test_no_regions_returns_empty_with_skip_reason(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["recamera/test.jpg"] = _make_test_image()

        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )
        handler = ImageCropHandler()

        step = _FakeStep(config_json={"image_source": "trigger", "regions": []})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.success
        assert result.data["count"] == 0
        assert result.data["images"] == []
        assert result.data["cropped_images"] == []
        assert any(s["reason"] == "no_regions" for s in result.data["skipped"])


class TestTriggerImageCrop:
    @pytest.mark.asyncio
    async def test_execute_with_trigger_image_uploads_crop_to_minio(self):
        fake_minio = _FakeMinio()
        test_jpg = _make_test_image(200, 150)
        fake_minio.objects["recamera/test.jpg"] = test_jpg

        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )
        handler = ImageCropHandler()

        step = _FakeStep(config_json={"image_source": "trigger", "regions": _STANDARD_REGIONS})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.success
        assert result.data["count"] == 1
        assert len(result.data["images"]) == 1
        assert len(result.data["cropped_images"]) == 1

        ci = result.data["cropped_images"][0]
        assert ci["region_id"] == "stove"
        assert ci["region_name"] == "Stove area"
        assert ci["source_type"] == "trigger"
        assert ci["source_object_name"] == "recamera/test.jpg"
        assert ci["original_width"] == 200
        assert ci["original_height"] == 150

        # Crop bounds: x=0.25, y=0.25, w=0.5, h=0.5 on 200x150
        # left=round(50)=50, top=round(37.5)=38, right=round(150)=150, bottom=round(112.5)=112
        assert ci["output_width"] == 100
        assert ci["output_height"] == 74
        assert ci["crop_box"]["unit"] == "ratio"

        # Verify the crop was uploaded to MinIO.
        assert len(fake_minio.objects) == 2  # original + crop
        crop_keys = [k for k in fake_minio.objects if k.startswith("pipeline/crops/")]
        assert len(crop_keys) == 1

    @pytest.mark.asyncio
    async def test_execute_with_pipeline_frame_uses_minio_key(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["cts/cam1/frame.jpg"] = _make_test_image(640, 480)

        trigger = _make_trigger()
        handler = ImageCropHandler()

        pipeline_data = {
            "steps": {
                "media_window_poll_1": {
                    "outputs": {
                        "frames": [
                            {
                                "minio_key": "cts/cam1/frame.jpg",
                                "camera_id": "cam1",
                                "room_name": "Living Room",
                                "frame_width": 640,
                                "frame_height": 480,
                            }
                        ]
                    }
                }
            }
        }

        step = _FakeStep(
            config_json={
                "image_source": "pipeline",
                "pipeline_image_path": "steps.media_window_poll_1.outputs.frames",
                "regions": _STANDARD_REGIONS,
            }
        )
        result = await handler.execute(
            step,
            _FakeExecution(),
            pipeline_data,
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.data["count"] == 1
        ci = result.data["cropped_images"][0]
        assert ci["source_type"] == "pipeline"
        assert ci["source_camera_id"] == "cam1"
        assert ci["source_room_name"] == "Living Room"
        assert ci["source_object_name"] == "cts/cam1/frame.jpg"

    @pytest.mark.asyncio
    async def test_execute_with_pipeline_crop_output_uses_object_name(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["pipeline/crops/100/1/stove_0.jpg"] = _make_test_image(100, 75)

        trigger = _make_trigger()
        handler = ImageCropHandler()

        pipeline_data = {
            "steps": {
                "crop_pass_1": {
                    "outputs": {
                        "cropped_images": [
                            {
                                "url": "http://minio.local/bucket/pipeline/crops/100/1/stove_0.jpg?sig=test",
                                "object_name": "pipeline/crops/100/1/stove_0.jpg",
                                "source_sensor_id": "kitchen_cam",
                                "source_room_name": "Kitchen",
                            }
                        ],
                        "images": [
                            "http://minio.local/bucket/pipeline/crops/100/1/stove_0.jpg?sig=test"
                        ],
                    }
                }
            }
        }

        step = _FakeStep(
            config_json={
                "image_source": "pipeline",
                "pipeline_image_path": "steps.crop_pass_1.outputs.images",
                "regions": _STANDARD_REGIONS,
            }
        )
        result = await handler.execute(
            step,
            _FakeExecution(),
            pipeline_data,
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.data["count"] == 1
        ci = result.data["cropped_images"][0]
        assert ci["source_type"] == "pipeline"


class TestMultipleRegions:
    @pytest.mark.asyncio
    async def test_execute_with_multiple_regions_emits_multiple_crops(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["recamera/test.jpg"] = _make_test_image(400, 300)

        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )
        handler = ImageCropHandler()

        regions = [
            {"id": "top_left", "name": "Top Left", "x": 0.0, "y": 0.0, "width": 0.5, "height": 0.5},
            {
                "id": "bottom_right",
                "name": "Bottom Right",
                "x": 0.5,
                "y": 0.5,
                "width": 0.5,
                "height": 0.5,
            },
        ]

        step = _FakeStep(config_json={"image_source": "trigger", "regions": regions})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.data["count"] == 2
        assert len(result.data["images"]) == 2
        assert len(result.data["cropped_images"]) == 2
        assert {ci["region_id"] for ci in result.data["cropped_images"]} == {
            "top_left",
            "bottom_right",
        }


class TestClamping:
    @pytest.mark.asyncio
    async def test_execute_clamps_region_to_image_bounds(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["recamera/test.jpg"] = _make_test_image(200, 150)

        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )
        handler = ImageCropHandler()

        # Region goes beyond image edges.
        regions = [
            {
                "id": "overflow",
                "name": "Overflow",
                "x": -0.5,
                "y": -0.5,
                "width": 2.0,
                "height": 2.0,
            },
        ]

        step = _FakeStep(config_json={"image_source": "trigger", "regions": regions})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio),
        )

        # Should still succeed — clamped to full image.
        assert result.data["count"] == 1
        ci = result.data["cropped_images"][0]
        assert ci["output_width"] == 200
        assert ci["output_height"] == 150


class TestTinyRegionSkip:
    @pytest.mark.asyncio
    async def test_execute_skips_tiny_region(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["recamera/test.jpg"] = _make_test_image(200, 150)

        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )
        handler = ImageCropHandler()

        # Tiny region (ratio 0.01 on a 200px image = 2px → below 8px minimum).
        regions = [
            {"id": "tiny", "name": "Tiny", "x": 0.0, "y": 0.0, "width": 0.01, "height": 0.01},
        ]

        step = _FakeStep(config_json={"image_source": "trigger", "regions": regions})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.data["count"] == 0
        assert result.data["images"] == []
        assert any(s["reason"] == "region_too_small" for s in result.data["skipped"])


class TestMediaCacheRegistration:
    @pytest.mark.asyncio
    async def test_execute_registers_media_cache_row(self):
        fake_minio = _FakeMinio()
        fake_minio.objects["recamera/test.jpg"] = _make_test_image(200, 150)
        mock_db = _make_mock_db()

        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )
        handler = ImageCropHandler()

        step = _FakeStep(config_json={"image_source": "trigger", "regions": _STANDARD_REGIONS})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio, db_factory=lambda: mock_db),
        )

        assert result.data["count"] == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()


class TestOutputSchema:
    def test_output_conforms_to_schema(self):
        """Verify the handler's output keys match its declared output_schema."""
        handler = ImageCropHandler()
        from backend.steps.base import StepResult

        result = StepResult(
            data={
                "images": ["http://minio/crop.jpg"],
                "cropped_images": [{"url": "http://minio/crop.jpg"}],
                "count": 1,
                "skipped": [],
                "cropped_at": datetime.now(UTC).isoformat(),
            },
        )
        assert_output_conforms_to_schema(handler, result)


class TestFetchFailed:
    @pytest.mark.asyncio
    async def test_fetch_failure_adds_skip_entry(self):
        fake_minio = _FakeMinio()
        # Don't add the image to fake_minio.objects — fetch will fail.

        trigger = _make_trigger(media_paths=["http://minio.local/bucket/missing.jpg?sig=test"])
        handler = ImageCropHandler()

        step = _FakeStep(config_json={"image_source": "trigger", "regions": _STANDARD_REGIONS})
        result = await handler.execute(
            step,
            _FakeExecution(),
            {},
            trigger,
            _make_services(minio_client=fake_minio),
        )

        assert result.data["count"] == 0
        assert any(s["reason"] == "fetch_failed" for s in result.data["skipped"])
