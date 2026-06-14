"""Metadata contract for the unified media window poll step."""

from __future__ import annotations

from typing import Literal

from backend.steps.base import StepMetadata

MediaSource = Literal["auto", "cts", "recamera"]


def build_media_window_metadata(default_source: MediaSource) -> StepMetadata:
    """Build metadata with a source default suitable for canonical or alias steps."""
    return StepMetadata(
        type_name="media_window_poll",
        display_name="Poll Media Window",
        category="perception",
        icon="mdi-camera-burst",
        description=(
            "Fetches a recent image window from CTS or reCamera aggregation. "
            "Auto mode prefers CTS when its live bucketizer is available."
        ),
        config_schema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["auto", "cts", "recamera"],
                    "default": default_source,
                },
                "duration_s": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 60,
                    "default": 10,
                },
                "sample_period_s": {
                    "type": "number",
                    "minimum": 0.2,
                    "maximum": 30,
                    "default": 1.0,
                },
                "cameras": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "rooms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "lookback_s": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 5,
                },
                "lookahead_s": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 30,
                    "default": 5,
                },
                "include_scene": {"type": "boolean", "default": False},
                "include_pose": {"type": "boolean", "default": False},
                "max_frames": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 30,
                },
                "sensor_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "room_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                },
                "since_minutes": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 60,
                    "default": 5,
                },
                "images_per_sensor": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 3,
                },
                "sensor_frame_limits": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "minimum": 1},
                    "default": {},
                },
                "max_images": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
                "chronological": {"type": "boolean", "default": True},
            },
        },
        default_config={
            "source": default_source,
            "duration_s": 10,
            "sample_period_s": 1.0,
            "cameras": [],
            "rooms": [],
            "lookback_s": 5,
            "lookahead_s": 5,
            "include_scene": False,
            "include_pose": False,
            "max_frames": 30,
            "sensor_ids": [],
            "room_names": [],
            "since_minutes": 5,
            "images_per_sensor": 3,
            "sensor_frame_limits": {},
            "max_images": 10,
            "chronological": True,
        },
        output_schema={
            "type": "object",
            "properties": {
                "trigger_id": {"type": ["string", "integer"]},
                "window_start": {"type": "string"},
                "window_end": {"type": "string"},
                "cameras": {"type": "array", "items": {"type": "string"}},
                "rooms": {"type": "array", "items": {"type": "string"}},
                "frames": {"type": "array"},
                "images": {"type": "array", "items": {"type": "string"}},
                "count": {"type": "integer"},
                "summary": {
                    "type": "object",
                    "properties": {
                        "distinct_identities": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "detection_count": {"type": "integer"},
                        "rooms": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "source": {"type": "string", "enum": ["cts", "recamera"]},
                "partial": {"type": "boolean"},
                "sensor_ids": {"type": "array", "items": {"type": "string"}},
                "room_names": {"type": "array", "items": {"type": "string"}},
                "since_minutes": {"type": "number"},
                "polled_at": {"type": "string"},
            },
            "required": [
                "window_start",
                "window_end",
                "cameras",
                "rooms",
                "frames",
                "images",
                "count",
                "summary",
                "source",
                "partial",
            ],
        },
        tags=("media", "cts", "recamera"),
    )
