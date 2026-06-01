"""Tests for UTC datetime serialization in API schemas."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.schemas.image import ActiveImageStateOut, ImageTemplateOut
from backend.schemas.room import RoomOut
from backend.schemas.rule import RuleListOut
from backend.schemas.sensor import SensorOut


@pytest.mark.parametrize(
    ("schema_cls", "payload", "field_name", "expected"),
    [
        (
            SensorOut,
            {
                "id": "cam-1",
                "name": "Camera 1",
                "room_id": 1,
                "sensor_type": "camera",
                "source": "local",
                "ha_entity_id": None,
                "enabled": True,
                "config_json": None,
                "created_at": datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York")),
            },
            "created_at",
            "2026-04-11T13:30:00Z",
        ),
        (
            RoomOut,
            {
                "id": 1,
                "name": "Kitchen",
                "ha_area_id": None,
                "floor": None,
                "metadata_json": None,
                "created_at": datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York")),
            },
            "created_at",
            "2026-04-11T13:30:00Z",
        ),
        (
            RuleListOut,
            {
                "id": 1,
                "name": "Rule",
                "description": None,
                "enabled": True,
                "trigger_types": ["sensor_event"],
                "cool_off_minutes": 5,
                "max_daily_triggers": 3,
                "max_concurrent_executions": 1,
                "execution_timeout_minutes": 5,
                "created_at": datetime(2026, 4, 11, 9, 30, 0, tzinfo=ZoneInfo("America/New_York")),
            },
            "created_at",
            "2026-04-11T13:30:00Z",
        ),
        (
            ImageTemplateOut,
            {
                "id": 1,
                "name": "Template",
                "description": None,
                "width": 800,
                "height": 480,
                "image_filename": "template.png",
                "font_filename": "font.ttf",
                "regions_json": [],
                "is_default": False,
                "created_at": datetime(2026, 4, 11, 13, 30, 0),
                "updated_at": None,
            },
            "created_at",
            "2026-04-11T13:30:00Z",
        ),
        (
            ActiveImageStateOut,
            {
                "id": 1,
                "sensor_id": "display-1",
                "template_id": None,
                "rendered_text": "Lunch",
                "expires_at": datetime(2026, 4, 11, 13, 30, 0),
                "updated_at": None,
            },
            "expires_at",
            "2026-04-11T13:30:00Z",
        ),
    ],
)
def test_schema_serializes_timestamps_with_z_suffix(
    schema_cls, payload: dict, field_name: str, expected: str
) -> None:
    data = schema_cls(**payload).model_dump(mode="json")

    assert data[field_name] == expected
