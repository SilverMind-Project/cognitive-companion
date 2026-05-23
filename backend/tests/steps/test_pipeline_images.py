"""Unit tests for :mod:`backend.steps._pipeline_images`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations.minio_client import MinioClient
from backend.steps._pipeline_images import (
    PipelineImageRef,
    image_refs_to_urls,
    normalize_image_value,
    resolve_pipeline_image_refs,
)
from backend.steps.base import ServiceContainer, TriggerContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_services(
    event_aggregator=None,
    minio_client=None,
) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        event_aggregator=event_aggregator,
        minio_client=minio_client,
    )


def _mock_minio() -> MagicMock:
    minio = MagicMock(spec=MinioClient)
    minio.generate_presigned_url.return_value = "http://minio.local/bucket/regenerated.jpg"
    return minio


# ---------------------------------------------------------------------------
# normalize_image_value
# ---------------------------------------------------------------------------


class TestNormalizeStringUrl:
    def test_returns_ref_with_url(self):
        refs = normalize_image_value("http://example.com/img.jpg", default_source_type="trigger")
        assert len(refs) == 1
        assert refs[0].url == "http://example.com/img.jpg"
        assert refs[0].object_name is None
        assert refs[0].source_type == "trigger"

    def test_https_url(self):
        refs = normalize_image_value("https://s3.local/bucket/key.jpg")
        assert refs[0].url == "https://s3.local/bucket/key.jpg"

    def test_data_uri(self):
        refs = normalize_image_value("data:image/jpeg;base64,abc123")
        assert refs[0].url == "data:image/jpeg;base64,abc123"

    def test_plain_string_treated_as_object_name(self):
        refs = normalize_image_value("recamera/20260523_120000_a1b2c3d4.jpg")
        assert len(refs) == 1
        assert refs[0].object_name == "recamera/20260523_120000_a1b2c3d4.jpg"
        assert refs[0].url is None


class TestNormalizeMinioKeyDict:
    def test_minio_key_returns_object_ref(self):
        refs = normalize_image_value(
            {"minio_key": "cts/frames/cam1/20260523_120000.jpg", "camera_id": "cam1", "room_name": "Kitchen"},
            default_source_type="cts_window",
        )
        assert len(refs) == 1
        assert refs[0].object_name == "cts/frames/cam1/20260523_120000.jpg"
        assert refs[0].source_type == "cts_window"
        assert refs[0].source_camera_id == "cam1"
        assert refs[0].source_room_name == "Kitchen"

    def test_url_key_dict(self):
        refs = normalize_image_value({"url": "http://example.com/img.jpg"}, default_source_type="pipeline")
        assert refs[0].url == "http://example.com/img.jpg"

    def test_image_url_key_dict(self):
        refs = normalize_image_value({"image_url": "http://example.com/img.jpg"}, default_source_type="pipeline")
        assert refs[0].url == "http://example.com/img.jpg"

    def test_object_name_key_dict(self):
        refs = normalize_image_value({"object_name": "pipeline/crops/123/stove.jpg"}, default_source_type="pipeline")
        assert refs[0].object_name == "pipeline/crops/123/stove.jpg"


class TestNormalizeCtsFrame:
    def test_cts_frame_preserves_camera_room_and_dimensions(self):
        refs = normalize_image_value(
            {
                "minio_key": "cts/20260523_cam1.jpg",
                "camera_id": "cam-cts-1",
                "room_name": "Living Room",
                "frame_width": 1920,
                "frame_height": 1080,
            },
            default_source_type="cts_window",
        )
        assert len(refs) == 1
        ref = refs[0]
        assert ref.object_name == "cts/20260523_cam1.jpg"
        assert ref.source_camera_id == "cam-cts-1"
        assert ref.source_room_name == "Living Room"
        assert ref.width == 1920
        assert ref.height == 1080


class TestNormalizeCropOutput:
    def test_crop_output_preserves_source_metadata(self):
        refs = normalize_image_value(
            {
                "url": "http://minio/crops/stove_0.jpg",
                "object_name": "pipeline/crops/123/45/stove_0.jpg",
                "source_sensor_id": "kitchen_recamera",
                "source_camera_id": None,
                "source_room_name": "Kitchen",
                "region_id": "stove",
                "region_name": "Stove area",
                "output_width": 640,
                "output_height": 480,
            },
            default_source_type="pipeline",
        )
        assert len(refs) == 1
        ref = refs[0]
        assert ref.url == "http://minio/crops/stove_0.jpg"
        assert ref.object_name == "pipeline/crops/123/45/stove_0.jpg"
        assert ref.source_sensor_id == "kitchen_recamera"
        assert ref.source_room_name == "Kitchen"
        assert "region_id" in ref.metadata
        assert ref.metadata["region_id"] == "stove"
        assert ref.metadata["region_name"] == "Stove area"


class TestNormalizeList:
    def test_normalize_list_flattens(self):
        refs = normalize_image_value(
            ["http://a.com/1.jpg", "http://b.com/2.jpg"],
            default_source_type="trigger",
        )
        assert len(refs) == 2
        assert refs[0].url == "http://a.com/1.jpg"
        assert refs[1].url == "http://b.com/2.jpg"

    def test_normalize_mixed_list(self):
        refs = normalize_image_value(
            ["http://a.com/1.jpg", {"url": "http://b.com/2.jpg"}],
            default_source_type="trigger",
        )
        assert len(refs) == 2

    def test_normalize_empty_list(self):
        assert normalize_image_value([]) == []


class TestNormalizeEdgeCases:
    def test_unknown_scalar_returns_empty(self):
        assert normalize_image_value(42) == []

    def test_none_returns_empty(self):
        assert normalize_image_value(None) == []


# ---------------------------------------------------------------------------
# resolve_pipeline_image_refs
# ---------------------------------------------------------------------------


class TestResolveTriggerSource:
    @pytest.mark.asyncio
    async def test_uses_trigger_media_paths(self):
        trigger = _make_trigger(media_paths=["http://minio/trigger1.jpg", "http://minio/trigger2.jpg"])
        services = _make_services()

        refs = await resolve_pipeline_image_refs(
            config={"image_source": "trigger"},
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 2
        assert all(r.source_type == "trigger" for r in refs)
        assert refs[0].url == "http://minio/trigger1.jpg"
        assert refs[1].url == "http://minio/trigger2.jpg"

    @pytest.mark.asyncio
    async def test_respects_trigger_images_count(self):
        trigger = _make_trigger(media_paths=["http://a/1.jpg", "http://a/2.jpg", "http://a/3.jpg"])
        services = _make_services()

        refs = await resolve_pipeline_image_refs(
            config={"image_source": "trigger", "trigger_images_count": 1},
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 1
        assert refs[0].url == "http://a/3.jpg"  # last N


class TestResolveAdditionalSource:
    @pytest.mark.asyncio
    async def test_uses_event_aggregator_with_room_filter(self):
        trigger = _make_trigger()
        agg = AsyncMock()
        agg.query_recent_media = AsyncMock(return_value=["http://extra/1.jpg"])

        services = _make_services(event_aggregator=agg)

        refs = await resolve_pipeline_image_refs(
            config={
                "image_source": "additional",
                "additional_room_names": ["Kitchen"],
                "max_images": 3,
            },
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 1
        assert refs[0].url == "http://extra/1.jpg"
        assert refs[0].source_type == "additional"
        agg.query_recent_media.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_trigger_for_default_source(self):
        trigger = _make_trigger(media_paths=["http://minio/t.jpg"])
        services = _make_services(event_aggregator=None)

        refs = await resolve_pipeline_image_refs(
            config={},
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 1
        assert refs[0].source_type == "trigger"


class TestResolvePipelineSource:
    @pytest.mark.asyncio
    async def test_reads_dotted_path_from_pipeline_data(self):
        trigger = _make_trigger()
        services = _make_services()
        pipeline_data = {
            "steps": {
                "recameras": {
                    "outputs": {
                        "images": ["http://minio/step_img.jpg"],
                    }
                }
            }
        }

        refs = await resolve_pipeline_image_refs(
            config={
                "image_source": "pipeline",
                "pipeline_image_path": "steps.recameras.outputs.images",
            },
            pipeline_data=pipeline_data,
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 1
        assert refs[0].url == "http://minio/step_img.jpg"
        assert refs[0].source_type == "pipeline"

    @pytest.mark.asyncio
    async def test_missing_pipeline_path_returns_empty_list(self):
        trigger = _make_trigger()
        services = _make_services()

        refs = await resolve_pipeline_image_refs(
            config={
                "image_source": "pipeline",
                "pipeline_image_path": "steps.nonexistent.outputs.images",
            },
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert refs == []


class TestResolveCtsWindowSource:
    @pytest.mark.asyncio
    async def test_reads_frames_path_from_pipeline_data(self):
        trigger = _make_trigger()
        services = _make_services()
        pipeline_data = {
            "steps": {
                "cts_window_poll_1": {
                    "outputs": {
                        "frames": [
                            {
                                "minio_key": "cts/cam1/frame.jpg",
                                "camera_id": "cam1",
                                "room_name": "Living Room",
                                "frame_width": 1920,
                                "frame_height": 1080,
                            }
                        ]
                    }
                }
            }
        }

        refs = await resolve_pipeline_image_refs(
            config={
                "image_source": "cts_window",
                "cts_frames_path": "steps.cts_window_poll_1.outputs.frames",
            },
            pipeline_data=pipeline_data,
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 1
        assert refs[0].object_name == "cts/cam1/frame.jpg"
        assert refs[0].source_camera_id == "cam1"
        assert refs[0].source_room_name == "Living Room"
        assert refs[0].width == 1920
        assert refs[0].height == 1080
        assert refs[0].source_type == "cts_window"


class TestResolveNoneSource:
    @pytest.mark.asyncio
    async def test_none_source_returns_empty(self):
        trigger = _make_trigger(media_paths=["http://minio/t.jpg"])
        services = _make_services()

        refs = await resolve_pipeline_image_refs(
            config={"image_source": "none"},
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert refs == []


class TestResolveMaxImagesCap:
    @pytest.mark.asyncio
    async def test_caps_total_images(self):
        trigger = _make_trigger(media_paths=["http://a/1.jpg", "http://a/2.jpg", "http://a/3.jpg"])
        services = _make_services()

        refs = await resolve_pipeline_image_refs(
            config={"image_source": "trigger", "max_images": 2},
            pipeline_data={},
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 2


class TestResolveMinioPresignedUrl:
    @pytest.mark.asyncio
    async def test_regenerates_url_for_object_name_refs(self):
        trigger = _make_trigger()
        services = _make_services(minio_client=_mock_minio())
        pipeline_data = {
            "steps": {
                "cts_window_poll_1": {
                    "outputs": {
                        "frames": [
                            {
                                "minio_key": "cts/cam1/frame.jpg",
                                "camera_id": "cam1",
                                "room_name": "Living Room",
                            }
                        ]
                    }
                }
            }
        }

        refs = await resolve_pipeline_image_refs(
            config={
                "image_source": "cts_window",
                "cts_frames_path": "steps.cts_window_poll_1.outputs.frames",
            },
            pipeline_data=pipeline_data,
            trigger=trigger,
            services=services,
        )

        assert len(refs) == 1
        assert refs[0].url == "http://minio.local/bucket/regenerated.jpg"
        assert refs[0].object_name == "cts/cam1/frame.jpg"


# ---------------------------------------------------------------------------
# image_refs_to_urls
# ---------------------------------------------------------------------------


class TestImageRefsToUrls:
    def test_regenerates_url_from_object_name(self):
        minio = _mock_minio()
        refs = [PipelineImageRef(object_name="cts/frame.jpg", source_type="cts_window")]

        urls = image_refs_to_urls(refs, minio_client=minio)

        assert urls == ["http://minio.local/bucket/regenerated.jpg"]
        minio.generate_presigned_url.assert_called_once_with("cts/frame.jpg")

    def test_keeps_existing_url_without_minio(self):
        refs = [PipelineImageRef(url="http://existing.com/img.jpg", source_type="trigger")]

        urls = image_refs_to_urls(refs, minio_client=None)

        assert urls == ["http://existing.com/img.jpg"]

    def test_url_takes_precedence_over_object_name(self):
        refs = [
            PipelineImageRef(
                url="http://existing.com/img.jpg",
                object_name="ignored/key.jpg",
                source_type="pipeline",
            )
        ]

        urls = image_refs_to_urls(refs, minio_client=_mock_minio())

        assert urls == ["http://existing.com/img.jpg"]

    def test_skips_refs_without_url_or_object_name(self):
        refs = [PipelineImageRef(source_type="unknown")]

        urls = image_refs_to_urls(refs, minio_client=None)

        assert urls == []

    def test_mixed_refs(self):
        minio = _mock_minio()
        refs = [
            PipelineImageRef(url="http://direct.com/img.jpg", source_type="trigger"),
            PipelineImageRef(object_name="needs/regeneration.jpg", source_type="pipeline"),
        ]

        urls = image_refs_to_urls(refs, minio_client=minio)

        assert len(urls) == 2
        assert urls[0] == "http://direct.com/img.jpg"
        assert urls[1] == "http://minio.local/bucket/regenerated.jpg"
