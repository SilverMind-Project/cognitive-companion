"""cts_window_poll pipeline step: on-demand CTS frame window.

Pulls a window of recent CTS frames enriched with detections, identities,
room dwells, and optionally scene captions.  Designed to be used as a
pipeline step triggered by reCamera sensor events, so the downstream LLM
step can reason over high-quality CTS data even though the trigger fired
from a low-resolution reCamera frame.

Payload shape is identical to the ``cts_window`` trigger payload (§4.2)
so downstream template expressions are symmetric across the two paths.
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
class CtsWindowPollHandler(StepHandler):
    """Poll CTS for a window of enriched frames."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="cts_window_poll",
            display_name="Poll CTS Window",
            category="perception",
            icon="mdi-camera-burst",
            description=(
                "Fetches a window of recent CTS frames enriched with detections, "
                "identities, room dwells, and optionally scene captions."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "duration_s": {
                        "type": "number",
                        "minimum": 1,
                        "maximum": 60,
                        "default": 10,
                        "description": "Total window duration in seconds.",
                    },
                    "sample_period_s": {
                        "type": "number",
                        "minimum": 0.2,
                        "maximum": 30,
                        "default": 1.0,
                        "description": "Downsample to one frame per this many seconds.",
                    },
                    "cameras": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Camera IDs to include (empty = all).",
                    },
                    "rooms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Room names to include (empty = all).",
                    },
                    "lookback_s": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 30,
                        "default": 5,
                        "description": "Seconds before trigger time to include.",
                    },
                    "lookahead_s": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 30,
                        "default": 5,
                        "description": "Seconds after trigger time to wait and collect.",
                    },
                    "include_scene": {
                        "type": "boolean",
                        "default": False,
                        "description": "Run scene analysis on sampled frames.",
                    },
                    "include_pose": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include pose keypoints (requires TD-005).",
                    },
                    "max_frames": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                        "default": 30,
                        "description": "Maximum total frames to return.",
                    },
                },
                "required": ["duration_s", "sample_period_s"],
            },
            default_config={
                "duration_s": 10,
                "sample_period_s": 1.0,
                "lookback_s": 5,
                "lookahead_s": 5,
                "include_scene": False,
                "include_pose": False,
                "max_frames": 30,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "trigger_id": {"type": "string"},
                    "window_start": {"type": "string"},
                    "window_end": {"type": "string"},
                    "cameras": {"type": "array", "items": {"type": "string"}},
                    "rooms": {"type": "array", "items": {"type": "string"}},
                    "frames": {"type": "array"},
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
                    "partial": {"type": "boolean"},
                },
            },
            tags=("cts",),
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}
        sample_period_s = float(config.get("sample_period_s", 1.0))
        lookback_s = float(config.get("lookback_s", 5))
        lookahead_s = float(config.get("lookahead_s", 5))
        cameras: list[str] | None = config.get("cameras") or None
        rooms: list[str] | None = config.get("rooms") or None
        include_scene = bool(config.get("include_scene", False))
        max_frames = int(config.get("max_frames", 30))

        now = datetime.now(UTC)
        window_start = now.timestamp() - lookback_s

        # Step 1: Pull historical frames from the in-memory bucketizer buffer
        # (which is the canonical recent-frame store shared with the live view).
        #
        # The bucketizer is wired in Phase 3 (CtsEventBucketizer). Until then
        # ServiceContainer has no `bucketizer` attribute, so we log a warning
        # and return an empty window with `partial=True` so downstream steps
        # can branch on it rather than silently receiving stale data.
        frames: list[dict[str, Any]] = []

        # Collect from the bucketizer's per-camera buffers.
        bucketizer = _get_bucketizer(services)
        if bucketizer is None:
            logger.warning(
                "cts_window_poll_no_bucketizer",
                execution_id=str(execution.id),
                msg=(
                    "CtsEventBucketizer is not wired into ServiceContainer. "
                    "Phase 3 must be completed before cts_window_poll can return "
                    "live CTS frames. Returning empty window with partial=True."
                ),
            )
        if bucketizer is not None:
            target_cameras = cameras or list(bucketizer.buffer_stats().keys())
            for cam_id in target_cameras:
                cam_frames = bucketizer.forward_buffer(
                    window_id=execution.id,
                    camera_id=cam_id,
                    lookahead_s=lookback_s + lookahead_s,
                )
                for f in cam_frames:
                    try:
                        evt_ts = datetime.fromisoformat(f.get("event_time", ""))
                    except ValueError, TypeError:
                        continue
                    if evt_ts.timestamp() >= window_start:
                        if rooms and f.get("room_name") not in rooms:
                            continue
                        frames.append(f)

        # Step 2: Downsample to sample_period_s.
        frames.sort(key=lambda f: f.get("event_time", ""))
        downsampled: list[dict[str, Any]] = []
        last_kept: float | None = None
        for f in frames:
            try:
                ts = datetime.fromisoformat(f["event_time"]).timestamp()
            except ValueError, KeyError, TypeError:
                continue
            if last_kept is None or (ts - last_kept) >= sample_period_s:
                downsampled.append(f)
                last_kept = ts
                if len(downsampled) >= max_frames:
                    break

        # Step 3: Optionally augment with scene captions.
        if include_scene and services.scene_analysis_client is not None:
            for f in downsampled[:max_frames]:
                try:
                    result = await services.scene_analysis_client.analyze(
                        f.get("minio_key", ""),
                    )
                    if result:
                        f["scene_caption"] = (
                            result
                            if isinstance(result, str)
                            else getattr(result, "caption", str(result))
                        )
                except Exception:
                    logger.exception("cts_window_poll_scene_error", minio_key=f.get("minio_key"))

        # Step 4: Build summary.
        distinct_ids: set[str] = set()
        rooms_seen: set[str] = set()
        detection_count = 0
        for f in downsampled:
            detection_count += f.get("detection_count", len(f.get("detections", [])))
            for det in f.get("detections", []):
                iid = det.get("identity_id", "")
                if iid:
                    distinct_ids.add(iid)
            room = f.get("room_name", "")
            if room:
                rooms_seen.add(room)

        return StepResult(
            data={
                "trigger_id": execution.id,
                "window_start": datetime.fromtimestamp(window_start, tz=UTC).isoformat(),
                "window_end": now.isoformat(),
                "cameras": sorted(cameras) if cameras else [],
                "rooms": sorted(rooms_seen),
                "frames": downsampled,
                "summary": {
                    "distinct_identities": sorted(distinct_ids),
                    "detection_count": detection_count,
                    "rooms": sorted(rooms_seen),
                },
                "partial": bucketizer is None
                or (len(downsampled) < len(frames) if frames else False),
            }
        )


def _get_bucketizer(services: ServiceContainer) -> Any:
    """Resolve the CtsEventBucketizer from the service container or app state.

    The bucketizer is attached to ``app.state.cts_runtime.bucketizer``
    during CTS startup.  When the step runs inside a pipeline execution
    there is no direct reference to the FastAPI app, so we reach through
    the ``services`` container (which is populated from the lifespan).
    """
    # The ServiceContainer currently has no bucketizer slot, but the
    # CTS runtime is accessible via app.state. In a full implementation,
    # add a ``bucketizer`` attribute to ServiceContainer and populate
    # it in the lifespan.
    return getattr(services, "bucketizer", None)
