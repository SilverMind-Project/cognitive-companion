"""Unit tests for :class:`~backend.steps.builtin.llm_call.LLMCallHandler`."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations.minio_client import MinioClient
from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.llm_call import LLMCallHandler

_HANDLER = LLMCallHandler()
_FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 12


# -- Helpers ----------------------------------------------------------------


@dataclass
class _FakeExecution:
    id: int = 1
    rule: object = None


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)


def _make_step(config: dict | None = None) -> _FakeStep:
    return _FakeStep(config_json=config or {})


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
    llm_model_registry=None,
    event_aggregator=None,
    minio_client=None,
) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        llm_model_registry=llm_model_registry,
        event_aggregator=event_aggregator,
        minio_client=minio_client,
    )


def _make_registry(model_cfg, provider):
    registry = MagicMock()
    registry.get_provider = MagicMock(return_value=provider)
    registry.get_config = MagicMock(return_value=model_cfg)
    return registry


def _make_model_cfg(capabilities=None):
    cfg = MagicMock()
    cfg.capabilities = capabilities or []
    return cfg


def _make_provider(response: str = "ok"):
    provider = AsyncMock()
    provider.call = AsyncMock(return_value=response)
    return provider


def _mock_minio(objects: dict | None = None):
    minio = MagicMock(spec=MinioClient)
    store = objects or {}

    async def _get(key):
        return store.get(key)

    minio.async_get_object = _get
    minio.generate_presigned_url = lambda k, expiration=3600: (
        f"http://minio.local/bucket/{k}?sig=test"
    )
    minio.extract_object_name = lambda u: u.split("/bucket/", 1)[1].split("?", 1)[0]
    return minio


# -- Metadata tests --------------------------------------------------------


class TestMetadata:
    def test_type_name(self):
        assert _HANDLER.metadata().type_name == "llm_call"

    def test_default_image_source_is_none(self):
        assert _HANDLER.metadata().default_config["image_source"] == "none"

    def test_image_source_enum_includes_pipeline_and_cts(self):
        enum = _HANDLER.metadata().config_schema["properties"]["image_source"]["enum"]
        assert "pipeline" in enum
        assert "cts_window" not in enum
        assert "none" in enum


# -- Downstream image source tests -----------------------------------------


class TestPipelineImageSource:
    @pytest.mark.asyncio
    async def test_vision_model_with_pipeline_image_source_passes_crop_urls(self):
        minio = _mock_minio({"pipeline/crops/100/1/stove.jpg": _FAKE_JPEG})
        provider = _make_provider("analysis result")
        model_cfg = _make_model_cfg(["vision", "text"])
        registry = _make_registry(model_cfg, provider)
        services = _make_services(llm_model_registry=registry, minio_client=minio)

        pipeline_data = {
            "steps": {
                "crop_stove": {
                    "outputs": {
                        "images": [
                            "http://minio.local/bucket/pipeline/crops/100/1/stove.jpg?sig=test",
                        ]
                    }
                }
            }
        }

        config = {
            "model_id": "test-vision",
            "image_source": "pipeline",
            "pipeline_image_path": "steps.crop_stove.outputs.images",
            "prompt": "What do you see?",
        }
        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )
        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        assert call_kwargs["media_paths"] is not None
        assert len(call_kwargs["media_paths"]) > 0
        # The URL should contain the presigned path
        assert any("pipeline/crops/100/1/stove.jpg" in p for p in call_kwargs["media_paths"])

    @pytest.mark.asyncio
    async def test_vision_model_with_pipeline_source_passes_presigned_urls(self):
        minio = _mock_minio({"cts/cam1/frame.jpg": _FAKE_JPEG})
        provider = _make_provider("analysis")
        model_cfg = _make_model_cfg(["vision"])
        registry = _make_registry(model_cfg, provider)
        services = _make_services(llm_model_registry=registry, minio_client=minio)

        pipeline_data = {
            "steps": {
                "media_window_poll_1": {
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
        config = {
            "model_id": "test-vision",
            "image_source": "pipeline",
            "pipeline_image_path": "steps.media_window_poll_1.outputs.frames",
            "prompt": "Describe the scene.",
        }
        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            _make_trigger(),
            services,
        )
        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        assert call_kwargs["media_paths"] is not None
        assert any("cts/cam1/frame.jpg" in p for p in call_kwargs["media_paths"])

    @pytest.mark.asyncio
    async def test_text_model_skips_pipeline_image_resolution(self):
        provider = _make_provider("text response")
        model_cfg = _make_model_cfg(["text"])  # no vision
        registry = _make_registry(model_cfg, provider)
        services = _make_services(llm_model_registry=registry)

        config = {
            "model_id": "test-text",
            "image_source": "pipeline",
            "pipeline_image_path": "steps.crop_stove.outputs.images",
            "prompt": "Hello",
        }
        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        # No media_paths when model lacks vision
        assert call_kwargs.get("media_paths") is None or call_kwargs.get("media_paths") == []


class TestAnnotatedImage:
    @pytest.mark.asyncio
    async def test_use_annotated_image_still_prepends_data_url(self):
        provider = _make_provider("seen")
        model_cfg = _make_model_cfg(["vision"])
        registry = _make_registry(model_cfg, provider)
        services = _make_services(llm_model_registry=registry)

        config = {
            "model_id": "test-vision",
            "image_source": "trigger",
            "use_annotated_image": True,
            "prompt": "Who is this?",
        }
        pipeline_data = {"annotated_image": "base64_fake_annotated_image_data"}
        trigger = _make_trigger(
            media_paths=["http://minio.local/bucket/recamera/test.jpg?sig=test"]
        )

        await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            pipeline_data,
            trigger,
            services,
        )
        provider.call.assert_called_once()
        call_kwargs = provider.call.call_args.kwargs
        mp = call_kwargs["media_paths"]
        # Annotated image (data URI) should be first
        assert any("data:image/jpeg;base64,base64_fake" in p for p in mp)


class TestOutputSchema:
    def test_output_conforms_to_schema(self):
        from backend.steps.base import StepResult

        result = StepResult(
            data={
                "llm_response": "test result",
                "logic_response": None,
                "vision_response": None,
                "translation": None,
                "notification_suppressed": False,
            },
        )
        assert_output_conforms_to_schema(_HANDLER, result)
