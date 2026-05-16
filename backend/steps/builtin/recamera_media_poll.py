"""recamera_media_poll pipeline step: on-demand reCamera image snapshot.

Fetches recent images from the reCamera MediaCache (via EventAggregator)
and returns them as a list of presigned MinIO URLs. This is a *snapshot*
step: it reads what is currently in the cache and returns immediately.
If the pipeline needs to wait for new events to accumulate first, place a
``wait`` step before this one.

The output shape is intentionally symmetric with the ``cts_window`` trigger
payload so downstream template expressions can reference image metadata
regardless of which camera path triggered the rule.

Typical usage::

    reCamera sensor fires
    → recamera_media_poll  (collect recent images from 1..N sensors/rooms)
    → condition            (branch on count)
    → scene_analysis / llm_call (analyze the images)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


@StepRegistry.register
class RecameraMediaPollHandler(StepHandler):
    """Fetch recent reCamera images from the MediaCache via EventAggregator."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="recamera_media_poll",
            display_name="Poll reCamera Media",
            category="perception",
            icon="mdi-camera-wireless-outline",
            description=(
                "Fetches recent images from the reCamera MediaCache and returns "
                "presigned URLs. Snapshot semantics: reads what is currently in "
                "cache and returns immediately. Place a 'wait' step before this "
                "one if events need time to accumulate."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "reCamera sensor IDs to include. Empty means all "
                            "cameras (subject to room_names filter if set)."
                        ),
                    },
                    "room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Room names to include. When combined with sensor_ids, "
                            "only sensors in these rooms are returned."
                        ),
                    },
                    "since_minutes": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 60,
                        "default": 5,
                        "description": (
                            "Return images captured within the last N minutes. "
                            "Images older than the MediaCache retention window "
                            "are never returned regardless of this setting."
                        ),
                    },
                    "images_per_sensor": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 3,
                        "description": (
                            "Maximum images returned per sensor when sensor_ids "
                            "are specified. Ignored when only room_names are used."
                        ),
                    },
                    "sensor_frame_limits": {
                        "type": "object",
                        "description": (
                            "Per-sensor overrides for images_per_sensor. "
                            "Keys are sensor IDs, values are integer frame limits."
                        ),
                        "additionalProperties": {"type": "integer"},
                    },
                    "max_images": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 10,
                        "description": "Hard cap on total images returned across all sensors.",
                    },
                    "chronological": {
                        "type": "boolean",
                        "default": True,
                        "description": (
                            "When true, images within each sensor group are sorted "
                            "oldest-first (better for temporal reasoning). "
                            "When false, newest-first."
                        ),
                    },
                },
                "required": [],
            },
            default_config={
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
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Presigned MinIO URLs for the collected images.",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of images returned.",
                    },
                    "sensor_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sensor IDs that were queried.",
                    },
                    "room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Room names that were queried.",
                    },
                    "since_minutes": {
                        "type": "number",
                        "description": "Lookback window used.",
                    },
                    "polled_at": {
                        "type": "string",
                        "description": "ISO-8601 UTC timestamp when the poll ran.",
                    },
                },
            },
            tags=("recamera", "media"),
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        if services.event_aggregator is None:
            logger.warning(
                "recamera_media_poll_no_aggregator",
                execution_id=str(execution.id),
                msg="EventAggregator is not available. Cannot fetch reCamera images.",
            )
            return StepResult(
                success=False,
                data={
                    "images": [],
                    "count": 0,
                    "sensor_ids": [],
                    "room_names": [],
                    "since_minutes": 0,
                    "polled_at": datetime.now(UTC).isoformat(),
                },
            )

        config: dict[str, Any] = step.config_json or {}
        sensor_ids: list[str] = config.get("sensor_ids") or []
        room_names: list[str] = config.get("room_names") or []
        since_minutes: float = float(config.get("since_minutes", 5))
        images_per_sensor: int = int(config.get("images_per_sensor", 3))
        sensor_frame_limits: dict[str, int] = config.get("sensor_frame_limits") or {}
        max_images: int = int(config.get("max_images", 10))
        chronological: bool = bool(config.get("chronological", True))

        polled_at = datetime.now(UTC)

        images: list[str]
        if sensor_ids:
            images = await services.event_aggregator.query_media_by_sensor(
                sensor_ids_ordered=sensor_ids,
                images_per_sensor=images_per_sensor,
                sensor_frame_limits=sensor_frame_limits or None,
                max_images=max_images,
                since_minutes=since_minutes,
                chronological=chronological,
            )
        else:
            images = await services.event_aggregator.query_recent_media(
                sensor_ids=None,
                room_names=room_names if room_names else None,
                limit=max_images,
                since_minutes=since_minutes,
            )

        logger.info(
            "recamera_media_poll_complete",
            execution_id=str(execution.id),
            count=len(images),
            sensor_ids=sensor_ids,
            room_names=room_names,
            since_minutes=since_minutes,
        )

        return StepResult(
            data={
                "images": images,
                "count": len(images),
                "sensor_ids": sensor_ids,
                "room_names": room_names,
                "since_minutes": since_minutes,
                "polled_at": polled_at.isoformat(),
            }
        )
