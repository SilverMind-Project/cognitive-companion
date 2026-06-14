"""Backward-compatible alias for the unified media window poll step."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from backend.steps import StepRegistry
from backend.steps.base import StepMetadata
from backend.steps.builtin.media_window_poll import MediaWindowPollHandler


@StepRegistry.register
class CtsWindowPollHandler(MediaWindowPollHandler):
    """Legacy ``cts_window_poll`` step type backed by the unified handler."""

    DEFAULT_SOURCE = "cts"

    @classmethod
    def metadata(cls) -> StepMetadata:
        metadata = super().metadata()
        config_schema = deepcopy(metadata.config_schema)
        config_schema["properties"]["source"]["default"] = "cts"
        return replace(
            metadata,
            type_name="cts_window_poll",
            display_name="Poll CTS Window",
            description=(
                "Fetches a window of recent image-eligible CTS frames enriched "
                "with detections, identities, and optional scene captions."
            ),
            config_schema=config_schema,
            default_config={**metadata.default_config, "source": "cts"},
            tags=("cts", "media"),
        )
