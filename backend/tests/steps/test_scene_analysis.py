"""Unit tests for :class:`~backend.steps.builtin.scene_analysis.SceneAnalysisHandler`.

HTTP fetches are intercepted by patching httpx.AsyncClient; no real network or
scene-analysis-service is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.minio_client import MinioClient
from backend.integrations.scene_analysis_client import (
    SceneAnalysisClient,
    SceneAnalyzeResult,
    SceneDetection,
    SceneHazardAlert,
)
from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.scene_analysis import SceneAnalysisHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIO_URL = "http://minio.nanai.internal/ai-media/cam1/frame.jpg"
_MINIO_URL2 = "http://minio.nanai.internal/ai-media/cam2/frame.jpg"
_FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 12  # minimal JPEG header bytes


@dataclass
class _FakeExecution:
    id: int = 1


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
    scene_analysis_client=None,
    event_aggregator=None,
    minio_client=None,
) -> ServiceContainer:
    return ServiceContainer(
        db_factory=MagicMock(),
        scene_analysis_client=scene_analysis_client,
        event_aggregator=event_aggregator,
        minio_client=minio_client,
    )


def _mock_client(result: SceneAnalyzeResult | None = None) -> AsyncMock:
    client = AsyncMock(spec=SceneAnalysisClient)
    client.configured = True
    client.analyze = AsyncMock(
        return_value=result
        or SceneAnalyzeResult(
            detections=[],
            description="",
            embedding=[],
            hazards=[],
        )
    )
    return client


def _patch_http(content: bytes | None = _FAKE_JPEG, status_code: int = 200):
    """Context manager that stubs httpx.AsyncClient.get inside _fetch_image."""
    mock_response = MagicMock()
    mock_response.content = content
    mock_response.raise_for_status = MagicMock(
        side_effect=None if status_code < 400 else Exception("HTTP error")
    )

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    mock_client_instance.get = AsyncMock(return_value=mock_response)

    return patch(
        "backend.steps.builtin.scene_analysis.httpx.AsyncClient",
        return_value=mock_client_instance,
    )


_HANDLER = SceneAnalysisHandler()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_type_name(self):
        assert _HANDLER.metadata().type_name == "scene_analysis"

    def test_category(self):
        assert _HANDLER.metadata().category == "perception"

    def test_default_config_has_expected_keys(self):
        keys = _HANDLER.metadata().default_config.keys()
        assert "run_detect" in keys
        assert "run_describe" in keys
        assert "max_images" in keys
        assert "image_source" in keys
        assert "additional_sensor_ids" in keys

    def test_default_image_source_is_trigger(self):
        assert _HANDLER.metadata().default_config["image_source"] == "trigger"


# ---------------------------------------------------------------------------
# Early exits
# ---------------------------------------------------------------------------


class TestEarlyExits:
    async def test_returns_empty_when_no_client(self):
        services = _make_services(scene_analysis_client=None)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.success is True
        assert result.data["scene_detections"] == []

    async def test_returns_empty_when_client_not_configured(self):
        client = _mock_client()
        client.configured = False
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(media_paths=[_MINIO_URL]), services
        )
        assert result.data["scene_detections"] == []
        client.analyze.assert_not_called()

    async def test_returns_empty_when_no_media_paths(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(media_paths=[]), services
        )
        assert result.data["scene_detections"] == []
        client.analyze.assert_not_called()

    async def test_returns_empty_when_url_fetch_fails(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        with _patch_http(status_code=403):
            result = await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        assert result.data["scene_detections"] == []
        client.analyze.assert_not_called()

    async def test_returns_empty_when_network_error(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_instance.get = AsyncMock(side_effect=Exception("connection refused"))

        with patch(
            "backend.steps.builtin.scene_analysis.httpx.AsyncClient",
            return_value=mock_client_instance,
        ):
            result = await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        assert result.data["scene_detections"] == []
        client.analyze.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_calls_analyze_with_image_bytes(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        client.analyze.assert_called_once()
        assert isinstance(client.analyze.call_args[0][0], bytes)

    async def test_result_data_has_expected_keys(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        assert "scene_images" in result.data
        assert "scene_detections" in result.data
        assert "scene_description" in result.data
        assert "scene_embedding" in result.data
        assert "scene_hazards" in result.data
        assert "scene_detector_available" in result.data
        assert "scene_describer_available" in result.data
        assert "scene_embedder_available" in result.data

    async def test_serialises_detections(self):
        det = SceneDetection(label="person", confidence=0.9, bbox=[0, 0, 100, 100], class_id=0)
        client = _mock_client(SceneAnalyzeResult(detections=[det]))
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        assert len(result.data["scene_detections"]) == 1
        assert result.data["scene_detections"][0]["label"] == "person"

    async def test_serialises_hazards(self):
        det = SceneDetection(label="fire", confidence=0.88, bbox=[0, 0, 50, 50], class_id=99)
        hazard = SceneHazardAlert(
            name="fire", severity="critical", description="Fire!", detection=det
        )
        client = _mock_client(SceneAnalyzeResult(detections=[det], hazards=[hazard]))
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        assert len(result.data["scene_hazards"]) == 1
        h = result.data["scene_hazards"][0]
        assert h["name"] == "fire"
        assert h["severity"] == "critical"
        assert h["detection"]["label"] == "fire"

    async def test_always_continues_pipeline(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        assert result.should_continue is True


# ---------------------------------------------------------------------------
# Config forwarding
# ---------------------------------------------------------------------------


class TestConfigForwarding:
    async def test_run_flags_forwarded(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        config = {
            "run_detect": True,
            "run_describe": False,
            "run_embed": True,
            "run_hazards": False,
        }
        with _patch_http():
            await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        call_kwargs = client.analyze.call_args.kwargs
        assert call_kwargs["run_detect"] is True
        assert call_kwargs["run_describe"] is False
        assert call_kwargs["run_embed"] is True
        assert call_kwargs["run_hazards"] is False

    async def test_max_images_limits_to_first_url(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            await _HANDLER.execute(
                _make_step({"max_images": 1}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        client.analyze.assert_called_once()


# ---------------------------------------------------------------------------
# Multi-image aggregation
# ---------------------------------------------------------------------------


class TestMultiImageAggregation:
    async def test_detections_aggregated_across_images(self):
        det1 = SceneDetection(label="person", confidence=0.9, bbox=[0, 0, 100, 100], class_id=0)
        det2 = SceneDetection(label="chair", confidence=0.7, bbox=[50, 50, 200, 200], class_id=1)
        client = AsyncMock(spec=SceneAnalysisClient)
        client.configured = True
        client.analyze = AsyncMock(
            side_effect=[
                SceneAnalyzeResult(detections=[det1]),
                SceneAnalyzeResult(detections=[det2]),
            ]
        )
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step({"max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        labels = [d["label"] for d in result.data["scene_detections"]]
        assert "person" in labels
        assert "chair" in labels
        assert client.analyze.call_count == 2

    async def test_description_joins_nonempty(self):
        client = AsyncMock(spec=SceneAnalysisClient)
        client.configured = True
        client.analyze = AsyncMock(
            side_effect=[
                SceneAnalyzeResult(description="A living room."),
                SceneAnalyzeResult(description="A kitchen with a stove."),
            ]
        )
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step({"max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        assert result.data["scene_description"] == "A living room.\n---\nA kitchen with a stove."

    async def test_description_skips_empty_entries(self):
        client = AsyncMock(spec=SceneAnalysisClient)
        client.configured = True
        client.analyze = AsyncMock(
            side_effect=[
                SceneAnalyzeResult(description=""),
                SceneAnalyzeResult(description="A kitchen with a stove."),
            ]
        )
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step({"max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        assert result.data["scene_description"] == "A kitchen with a stove."

    async def test_scene_images_has_per_image_entry(self):
        det = SceneDetection(label="person", confidence=0.9, bbox=[0, 0, 100, 100], class_id=0)
        client = AsyncMock(spec=SceneAnalysisClient)
        client.configured = True
        client.analyze = AsyncMock(
            side_effect=[
                SceneAnalyzeResult(detections=[det], description="Image one."),
                SceneAnalyzeResult(description="Image two."),
            ]
        )
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step({"max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        images = result.data["scene_images"]
        assert len(images) == 2
        assert images[0]["image_path"] == _MINIO_URL
        assert images[0]["scene_description"] == "Image one."
        assert len(images[0]["scene_detections"]) == 1
        assert images[0]["scene_detections"][0]["label"] == "person"
        assert images[1]["image_path"] == _MINIO_URL2
        assert images[1]["scene_description"] == "Image two."
        assert images[1]["scene_detections"] == []

    async def test_scene_images_empty_on_no_client(self):
        services = _make_services(scene_analysis_client=None)
        result = await _HANDLER.execute(
            _make_step(), _FakeExecution(), {}, _make_trigger(), services
        )
        assert result.data["scene_images"] == []

    async def test_hazards_aggregated_across_images(self):
        det = SceneDetection(label="fire", confidence=0.9, bbox=[0, 0, 10, 10], class_id=99)
        hazard1 = SceneHazardAlert(
            name="fire", severity="critical", description="Fire!", detection=det
        )
        hazard2 = SceneHazardAlert(
            name="smoke", severity="warning", description="Smoke!", detection=det
        )
        client = AsyncMock(spec=SceneAnalysisClient)
        client.configured = True
        client.analyze = AsyncMock(
            side_effect=[
                SceneAnalyzeResult(detections=[det], hazards=[hazard1]),
                SceneAnalyzeResult(detections=[det], hazards=[hazard2]),
            ]
        )
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step({"max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        hazard_names = {h["name"] for h in result.data["scene_hazards"]}
        assert "fire" in hazard_names
        assert "smoke" in hazard_names

    async def test_skips_unreadable_image_continues_rest(self):
        det = SceneDetection(label="person", confidence=0.9, bbox=[0, 0, 100, 100], class_id=0)
        client = _mock_client(SceneAnalyzeResult(detections=[det]))
        services = _make_services(scene_analysis_client=client)

        # First URL fails (403), second succeeds
        call_count = 0

        async def _fake_get(url):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.raise_for_status = MagicMock(side_effect=Exception("403"))
            else:
                mock_resp.content = _FAKE_JPEG
                mock_resp.raise_for_status = MagicMock()
            return mock_resp

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.get = _fake_get

        with patch(
            "backend.steps.builtin.scene_analysis.httpx.AsyncClient", return_value=mock_http
        ):
            result = await _HANDLER.execute(
                _make_step({"max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        assert len(result.data["scene_detections"]) == 1
        client.analyze.assert_called_once()


# ---------------------------------------------------------------------------
# Image source routing
# ---------------------------------------------------------------------------


class TestImageSource:
    async def test_trigger_source_uses_trigger_paths(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        with _patch_http():
            await _HANDLER.execute(
                _make_step({"image_source": "trigger", "max_images": 2}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        assert client.analyze.call_count == 2

    async def test_additional_source_uses_event_aggregator(self):
        client = _mock_client()
        agg = AsyncMock()
        agg.query_recent_media = AsyncMock(return_value=[_MINIO_URL])
        services = _make_services(scene_analysis_client=client, event_aggregator=agg)
        with _patch_http():
            await _HANDLER.execute(
                _make_step({"image_source": "additional"}),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[]),
                services,
            )
        agg.query_recent_media.assert_called_once()
        client.analyze.assert_called_once()

    async def test_both_source_combines_trigger_and_additional(self):
        client = AsyncMock(spec=SceneAnalysisClient)
        client.configured = True
        client.analyze = AsyncMock(return_value=SceneAnalyzeResult())
        agg = AsyncMock()
        agg.query_recent_media = AsyncMock(return_value=[_MINIO_URL2])
        services = _make_services(scene_analysis_client=client, event_aggregator=agg)
        config = {
            "image_source": "both",
            "max_images": 5,
            "additional_room_names": ["Kitchen"],
        }
        with _patch_http():
            await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL]),
                services,
            )
        # trigger gave 1 URL, additional room query gave 1 URL = 2 analyze calls
        assert client.analyze.call_count == 2

    async def test_additional_with_sensor_ids_uses_query_by_sensor(self):
        client = _mock_client()
        agg = AsyncMock()
        agg.query_media_by_sensor = AsyncMock(return_value=[_MINIO_URL])
        services = _make_services(scene_analysis_client=client, event_aggregator=agg)
        config = {
            "image_source": "additional",
            "additional_sensor_ids": ["cam-2"],
        }
        with _patch_http():
            await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[]),
                services,
            )
        agg.query_media_by_sensor.assert_called_once()
        client.analyze.assert_called_once()

    async def test_trigger_images_count_limits_trigger_frames(self):
        client = _mock_client()
        services = _make_services(scene_analysis_client=client)
        config = {
            "image_source": "trigger",
            "max_images": 5,
            "trigger_images_count": 1,
        }
        with _patch_http():
            await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                {},
                _make_trigger(media_paths=[_MINIO_URL, _MINIO_URL2]),
                services,
            )
        # Only the last 1 frame should be used
        client.analyze.assert_called_once()


# ---------------------------------------------------------------------------
# Downstream image source (Milestone 4)
# ---------------------------------------------------------------------------


def _mock_minio(objects: dict | None = None) -> MagicMock:
    """Fake MinioClient that serves objects from an in-memory dict."""
    minio = MagicMock(spec=MinioClient)
    store = objects or {}
    minio.objects = store

    async def _get_object(key):
        return store.get(key)

    minio.async_get_object = _get_object

    def _presigned(key, expiration=3600):
        return f"http://minio.local/bucket/{key}?sig=test"

    minio.generate_presigned_url = _presigned
    minio.extract_object_name = lambda url: url.split("/bucket/", 1)[1].split("?", 1)[0]
    return minio


class TestDownstreamImageSource:
    """Verify scene_analysis can consume crop / CTS / pipeline image outputs."""

    @pytest.mark.asyncio
    async def test_pipeline_image_source_reads_crop_images_path(self):
        """When image_source=pipeline and pipeline_image_path points to
        images[], each URL is fetched and analysed."""
        client = _mock_client()
        minio = _mock_minio({"pipeline/crops/100/1/stove_0.jpg": _FAKE_JPEG})
        services = _make_services(scene_analysis_client=client, minio_client=minio)

        pipeline_data = {
            "steps": {
                "crop_stove": {
                    "outputs": {
                        "images": [
                            "http://minio.local/bucket/pipeline/crops/100/1/stove_0.jpg?sig=test",
                        ]
                    }
                }
            }
        }

        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.crop_stove.outputs.images",
        }
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                pipeline_data,
                _make_trigger(),
                services,
            )
        assert result.data["scene_detections"] is not None

    @pytest.mark.asyncio
    async def test_pipeline_source_missing_path_returns_empty_result(self):
        """A pipeline_image_path that resolves to nothing returns empty."""
        client = _mock_client()
        minio = _mock_minio()
        services = _make_services(scene_analysis_client=client, minio_client=minio)

        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.nonexistent.outputs.images",
        }
        result = await _HANDLER.execute(
            _make_step(config),
            _FakeExecution(),
            {},
            _make_trigger(),
            services,
        )
        assert result.data["scene_images"] == []

    @pytest.mark.asyncio
    async def test_cts_window_source_reads_minio_keys(self):
        """CTS frame dicts with minio_key are resolved through MinIO."""
        client = _mock_client()
        minio = _mock_minio({"cts/cam1/frame.jpg": _FAKE_JPEG})
        services = _make_services(scene_analysis_client=client, minio_client=minio)

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
            "image_source": "cts_window",
            "cts_frames_path": "steps.media_window_poll_1.outputs.frames",
        }
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                pipeline_data,
                _make_trigger(),
                services,
            )
        # The presigned URL should have been generated
        assert len(result.data["scene_images"]) == 1
        assert "cts/cam1/frame.jpg" in result.data["scene_images"][0]["image_path"]

    @pytest.mark.asyncio
    async def test_pipeline_image_source_reads_cropped_image_refs(self):
        """When pipeline_image_path points to cropped_images[], object_names are used."""
        client = _mock_client()
        minio = _mock_minio({"pipeline/crops/100/1/stove.jpg": _FAKE_JPEG})
        services = _make_services(scene_analysis_client=client, minio_client=minio)

        pipeline_data = {
            "steps": {
                "crop_stove": {
                    "outputs": {
                        "cropped_images": [
                            {
                                "url": "http://minio/old.jpg",
                                "object_name": "pipeline/crops/100/1/stove.jpg",
                                "region_id": "stove",
                            }
                        ]
                    }
                }
            }
        }
        config = {
            "image_source": "pipeline",
            "pipeline_image_path": "steps.crop_stove.outputs.cropped_images",
        }
        with _patch_http():
            result = await _HANDLER.execute(
                _make_step(config),
                _FakeExecution(),
                pipeline_data,
                _make_trigger(),
                services,
            )
        # The cropped_images dict has url, so it passes through
        assert len(result.data["scene_images"]) == 1
        image_path = result.data["scene_images"][0]["image_path"]
        # The URL from cropped_images entry is used
        assert "minio/old.jpg" in image_path

    def test_output_conforms_to_schema(self):
        """SceneAnalysis metadata declares all output keys."""
        from backend.steps.base import StepResult

        result = StepResult(
            data={
                "scene_images": [],
                "scene_detections": [],
                "scene_description": "",
                "scene_embedding": [],
                "scene_hazards": [],
                "scene_detector_available": False,
                "scene_describer_available": False,
                "scene_embedder_available": False,
                "scene_memory_observation_id": None,
            },
        )
        assert_output_conforms_to_schema(_HANDLER, result)
