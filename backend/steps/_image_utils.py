"""Shared image-source resolution for step handlers.

scene_analysis, llm_call, and notification all share the same
"trigger / additional / both" branching pattern.  This module extracts
that logic so it lives in one place.
"""

from __future__ import annotations

from typing import Any

from backend.steps.base import TriggerContext


async def resolve_image_sources(
    config: dict,
    trigger: TriggerContext,
    event_aggregator: Any,
    *,
    config_prefix: str = "",
    default_max_images: int = 5,
    default_images_per_sensor: int = 1,
    sort_by_sensor: bool = False,
) -> list[str]:
    """Collect image paths from trigger media and/or additional cameras.

    Config keys read (prefixed with *config_prefix*):

    * ``<prefix>image_source`` — ``"trigger"`` | ``"additional"`` | ``"both"``
    * ``<prefix>trigger_images_count`` — max trigger frames (0 = unlimited)
    * ``<prefix>additional_sensor_ids`` / ``<prefix>additional_room_names``
    * ``<prefix>image_time_filter`` — ``{"since_minutes": N, ...}``
    * ``<prefix>max_images`` — overall cap (default: *default_max_images*)
    * ``<prefix>images_per_sensor`` — per-sensor cap
    * ``<prefix>sensor_frame_limits`` — per-sensor overrides
    """
    def _cfg(key: str) -> object:
        return config.get(f"{config_prefix}{key}")

    image_source: str = _cfg("image_source") or "trigger"
    max_images: int = int(_cfg("max_images") or default_max_images)
    media_paths: list[str] = []

    # -- trigger frames -------------------------------------------------------
    if image_source in ("trigger", "both"):
        frames = list(trigger.media_paths)
        trigger_count = _cfg("trigger_images_count")
        if trigger_count and trigger_count > 0:
            frames = frames[-trigger_count:]
        media_paths.extend(frames)

    # -- additional cameras ---------------------------------------------------
    if image_source in ("additional", "both") and event_aggregator:
        additional_sensors: list[str] = _cfg("additional_sensor_ids") or []
        additional_rooms: list[str] = _cfg("additional_room_names") or []
        time_filter: dict = _cfg("image_time_filter") or {}
        images_per_sensor: int = int(_cfg("images_per_sensor") or default_images_per_sensor)
        sensor_frame_limits: dict = _cfg("sensor_frame_limits") or {}
        time_kwargs = {
            "since_minutes": time_filter.get("since_minutes"),
            "time_start": time_filter.get("time_start"),
            "time_end": time_filter.get("time_end"),
        }

        if additional_rooms:
            extra = await event_aggregator.query_recent_media(
                sensor_ids=additional_sensors if additional_sensors else None,
                room_names=additional_rooms,
                limit=max_images,
                **time_kwargs,
            )
            media_paths.extend(extra)
        elif additional_sensors:
            extra = await event_aggregator.query_media_by_sensor(
                sensor_ids_ordered=additional_sensors,
                images_per_sensor=images_per_sensor,
                sensor_frame_limits=sensor_frame_limits,
                max_images=max_images,
                chronological=sort_by_sensor,
                **time_kwargs,
            )
            media_paths.extend(extra)
        elif image_source == "additional":
            extra = await event_aggregator.query_recent_media(
                sensor_ids=None,
                room_names=None,
                limit=max_images,
                **time_kwargs,
            )
            media_paths.extend(extra)

    return media_paths[:max_images]
