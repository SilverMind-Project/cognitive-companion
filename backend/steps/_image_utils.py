"""Shared image-source resolution for step handlers.

scene_analysis, llm_call, and notification all share the same
"trigger / additional / both" branching pattern.  This module extracts
that logic so it lives in one place.

The legacy :func:`resolve_image_sources` is now a thin wrapper around
:func:`~backend.steps._pipeline_images.resolve_pipeline_image_refs`.
New callers that need structured :class:`PipelineImageRef` objects
should import from ``_pipeline_images`` directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend.steps._pipeline_images import (
    image_refs_to_urls,
    resolve_pipeline_image_refs,
)
from backend.steps.base import ServiceContainer, TriggerContext

if TYPE_CHECKING:
    from backend.integrations.minio_client import MinioClient
    from backend.services.event_aggregator import EventAggregator


async def resolve_image_sources(
    config: dict,
    trigger: TriggerContext,
    event_aggregator: EventAggregator | None,
    *,
    config_prefix: str = "",
    default_max_images: int = 5,
    default_images_per_sensor: int = 1,
    sort_by_sensor: bool = False,
    pipeline_data: Mapping[str, object] | None = None,
    minio_client: MinioClient | None = None,
) -> list[str]:
    """Collect image URLs from trigger media and/or additional cameras.

    Config keys read (prefixed with *config_prefix*):

    * ``<prefix>image_source`` -- ``"trigger"`` | ``"additional"`` | ``"both"``
    * ``<prefix>trigger_images_count`` -- max trigger frames (0 = unlimited)
    * ``<prefix>additional_sensor_ids`` / ``<prefix>additional_room_names``
    * ``<prefix>image_time_filter`` -- ``{"since_minutes": N, ...}``
    * ``<prefix>max_images`` -- overall cap (default: *default_max_images*)
    * ``<prefix>images_per_sensor`` -- per-sensor cap
    * ``<prefix>sensor_frame_limits`` -- per-sensor overrides

    Also accepts *pipeline_data* and *minio_client* so that
    ``image_source="pipeline"``, ``image_source="media_window"``, and
    ``image_source="cts_window"`` sources work.
    """
    # Build a prefixed config view for the shared resolver.
    if config_prefix:
        prefixed: dict[str, object] = {}
        for k, v in config.items():
            if k.startswith(config_prefix):
                prefixed[k[len(config_prefix) :]] = v
    else:
        prefixed = dict(config)

    # Preserve explicit defaults so the shared resolver sees them even
    # when the key is not in the config dict.
    prefixed.setdefault("image_source", "trigger")

    services = ServiceContainer(
        db_factory=lambda: None,
        event_aggregator=event_aggregator,
        minio_client=minio_client,
    )

    refs = await resolve_pipeline_image_refs(
        prefixed,
        pipeline_data or {},
        trigger,
        services,
        default_image_source="trigger",
        default_max_images=default_max_images,
        default_images_per_sensor=default_images_per_sensor,
        sort_by_sensor=sort_by_sensor,
    )

    return image_refs_to_urls(refs, minio_client=minio_client)
