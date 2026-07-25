"""Unit tests for backend.steps.builtin.region_presence.RegionPresenceHandler."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from backend.steps._testing import assert_output_conforms_to_schema
from backend.steps.base import ServiceContainer, TriggerContext
from backend.steps.builtin.region_presence import RegionPresenceHandler


@dataclass
class _FakeStep:
    config_json: dict = field(default_factory=dict)
    id: int = 1
    label: str = "region_presence_1"


@dataclass
class _FakeExecution:
    id: int = 100


def _make_trigger() -> TriggerContext:
    return TriggerContext(trigger_type="sensor_event", sensor_id="cam-1", room_name="kitchen")


def _make_services() -> ServiceContainer:
    return ServiceContainer(db_factory=lambda: None)


def _rect_region(region_id="kettle_counter", name="Kettle counter", **overrides):
    region = {
        "id": region_id,
        "name": name,
        "x": 0.0,
        "y": 0.0,
        "width": 0.5,
        "height": 1.0,
    }
    region.update(overrides)
    return region


def _polygon_region(region_id="stove", name="Stove"):
    return {
        "id": region_id,
        "name": name,
        "points": [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]],
    }


def _detection(bbox=(0.1, 0.1, 0.2, 0.2), **extra):
    return {"label": "person", "confidence": 0.9, "bbox": list(bbox), "bbox_normalized": True, **extra}


@pytest.mark.asyncio
async def test_step_no_detections_returns_empty_success():
    handler = RegionPresenceHandler()
    step = _FakeStep(config_json={"regions": [_rect_region()]})

    result = await handler.execute(
        step, _FakeExecution(), {"scene_detections": []}, _make_trigger(), _make_services()
    )

    assert result.success is True
    assert result.data["in_region"] is False
    assert result.data["count"] == 0
    assert result.data["hits"] == []
    assert result.data["skipped"] == [{"reason": "no_detections"}]
    assert_output_conforms_to_schema(handler, result)


@pytest.mark.asyncio
async def test_step_no_regions_skips():
    handler = RegionPresenceHandler()
    step = _FakeStep(config_json={"regions": []})
    pipeline_data = {"scene_detections": [_detection()]}

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert result.data["skipped"] == [{"reason": "no_regions"}]
    assert result.data["count"] == 0
    assert_output_conforms_to_schema(handler, result)


@pytest.mark.asyncio
async def test_step_rect_and_polygon_regions_mixed():
    handler = RegionPresenceHandler()
    step = _FakeStep(
        config_json={"regions": [_rect_region(), _polygon_region()]},
    )
    pipeline_data = {
        "scene_detections": [
            _detection(bbox=(0.1, 0.1, 0.2, 0.2)),  # left half -> kettle_counter
            _detection(bbox=(0.7, 0.1, 0.8, 0.2)),  # right half -> stove
        ]
    }

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert result.data["in_region"] is True
    assert result.data["count"] == 2
    assert result.data["per_region"] == {"kettle_counter": 1, "stove": 1}
    assert_output_conforms_to_schema(handler, result)


@pytest.mark.asyncio
async def test_step_output_matches_output_schema():
    handler = RegionPresenceHandler()
    step = _FakeStep(config_json={"regions": [_rect_region()]})
    pipeline_data = {"scene_detections": [_detection()]}

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert_output_conforms_to_schema(handler, result)
    for hit in result.data["hits"]:
        assert {"region_id", "region_name", "label", "confidence", "anchor", "detection_index"} <= set(
            hit.keys()
        )


@pytest.mark.asyncio
async def test_step_dotted_detections_key():
    handler = RegionPresenceHandler()
    step = _FakeStep(
        config_json={
            "detections_key": "steps.scene_analysis_1.outputs.scene_detections",
            "regions": [_rect_region()],
        }
    )
    pipeline_data = {
        "steps": {
            "scene_analysis_1": {"outputs": {"scene_detections": [_detection()]}},
        }
    }

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert result.data["in_region"] is True
    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_step_unknown_bbox_space_is_skipped_not_failed():
    handler = RegionPresenceHandler()
    step = _FakeStep(config_json={"regions": [_rect_region()]})
    pipeline_data = {
        "scene_detections": [
            {"label": "person", "confidence": 0.9, "bbox": [10.0, 10.0, 20.0, 20.0]}
        ]
    }

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert result.success is True
    assert result.data["count"] == 0
    assert {"reason": "unknown_bbox_space", "detection_index": 0} in result.data["skipped"]


@pytest.mark.asyncio
async def test_step_pixel_bbox_with_image_dimensions_normalizes():
    """A stock scene_analysis -> region_presence chain (post image_width/height
    widening) must produce a real hit, not unknown_bbox_space."""
    handler = RegionPresenceHandler()
    step = _FakeStep(config_json={"regions": [_rect_region()]})
    pipeline_data = {
        "scene_detections": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": [32.0, 96.0, 64.0, 192.0],  # pixel-space, left half of a 320x240 image
                "image_width": 320,
                "image_height": 240,
            }
        ]
    }

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert result.data["skipped"] == []
    assert result.data["in_region"] is True
    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_step_camera_scoped_region_without_attribution_notes_unavailable():
    handler = RegionPresenceHandler()
    step = _FakeStep(
        config_json={"regions": [_rect_region(camera_id="cam-2")]},
    )
    pipeline_data = {"scene_detections": [_detection()]}

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    # No camera attribution on the detection -> region applies to all detections.
    assert result.data["count"] == 1
    assert {"reason": "camera_filter_unavailable"} in result.data["skipped"]


@pytest.mark.asyncio
async def test_step_camera_scoped_region_filters_when_attribution_present():
    handler = RegionPresenceHandler()
    step = _FakeStep(
        config_json={"regions": [_rect_region(camera_id="cam-2")]},
    )
    pipeline_data = {
        "scene_detections": [
            _detection(bbox=(0.1, 0.1, 0.2, 0.2), camera_id="cam-1"),
            _detection(bbox=(0.1, 0.1, 0.2, 0.2), camera_id="cam-2"),
        ]
    }

    result = await handler.execute(
        step, _FakeExecution(), pipeline_data, _make_trigger(), _make_services()
    )

    assert result.data["count"] == 1
    assert result.data["hits"][0]["detection_index"] == 1
