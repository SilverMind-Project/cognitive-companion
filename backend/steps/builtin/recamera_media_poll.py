"""Backward-compatible alias for the unified media window poll step."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from backend.steps import StepRegistry
from backend.steps.base import StepMetadata
from backend.steps.builtin.media_window_poll import MediaWindowPollHandler


@StepRegistry.register
class RecameraMediaPollHandler(MediaWindowPollHandler):
    """Legacy ``recamera_media_poll`` step type backed by the unified handler."""

    DEFAULT_SOURCE = "recamera"

    @classmethod
    def metadata(cls) -> StepMetadata:
        metadata = super().metadata()
        config_schema = deepcopy(metadata.config_schema)
        config_schema["properties"]["source"]["default"] = "recamera"
        return replace(
            metadata,
            type_name="recamera_media_poll",
            display_name="Poll reCamera Media",
            icon="mdi-camera-wireless-outline",
            description=(
                "Fetches recent images from the reCamera MediaCache and returns "
                "presigned URLs with snapshot semantics."
            ),
            config_schema=config_schema,
            default_config={**metadata.default_config, "source": "recamera"},
            tags=("recamera", "media"),
        )
