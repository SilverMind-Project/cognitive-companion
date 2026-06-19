"""Unified on-demand media window step for CTS and reCamera sources."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.guided_task.camera_selection import ResolvedCamera
from backend.services.media_window_frames import (
    CtsFrameWindowConfig,
    collect_recent_cts_frames,
    collect_recent_frames_multi_source,
    parse_event_time,
)
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)
from backend.steps.media_window_contract import (
    MediaSource,
    build_media_window_metadata,
)

logger = get_logger(__name__)


@StepRegistry.register
class MediaWindowPollHandler(StepHandler):
    """Poll recent images from CTS or reCamera aggregation.

    ``source="auto"`` prefers CTS whenever a bucketizer is available and
    otherwise uses reCamera.

    Full metadata buffer feeds trigger evaluation and the detection/identity
    summary. ``image_eligible`` (aggregator ceiling) filters the image candidate
    set. ``sample_period_s`` further downsamples that subset per rule.
    Effective image rate = min(aggregator ceiling, per-rule step intent).
    """

    DEFAULT_SOURCE: MediaSource = "auto"

    @classmethod
    def metadata(cls) -> StepMetadata:
        return build_media_window_metadata(cls.DEFAULT_SOURCE)

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config: dict[str, Any] = step.config_json or {}

        # 1. Resolve source-tagged cameras
        injected_cameras = pipeline_data.get("_cameras") if pipeline_data else None
        configured_source = str(config.get("source", self.DEFAULT_SOURCE))
        explicit_cameras = list(config.get("cameras") or [])

        resolved_cameras: list[ResolvedCamera] = []

        if configured_source == "auto" and not explicit_cameras and injected_cameras:
            for c in injected_cameras:
                resolved_cameras.append(ResolvedCamera(id=c["id"], source=c["source"]))
        elif explicit_cameras:
            resolver = services.camera_source_resolver
            for cid in explicit_cameras:
                if resolver is not None:
                    src = resolver(cid)
                    if src is not None:
                        resolved_cameras.append(ResolvedCamera(id=cid, source=src))
                    else:
                        logger.warning("media_window_poll_camera_source_unknown", camera_id=cid)
                        resolved_cameras.append(
                            ResolvedCamera(
                                id=cid, source="recamera" if cid.startswith("recamera:") else "cts"
                            )
                        )
                else:
                    resolved_cameras.append(
                        ResolvedCamera(
                            id=cid, source="recamera" if cid.startswith("recamera:") else "cts"
                        )
                    )

        # 2. Check if we have mixed sources
        has_cts = any(c.source == "cts" for c in resolved_cameras)
        has_recamera = any(c.source == "recamera" for c in resolved_cameras)

        if has_cts and has_recamera:
            return await self._execute_mixed(config, execution, resolved_cameras, services)
        elif resolved_cameras:
            if has_cts:
                return await self._execute_cts(
                    config, execution, services, cameras=[c.id for c in resolved_cameras]
                )
            else:
                return await self._execute_recamera(
                    config, execution, services, sensor_ids=[c.id for c in resolved_cameras]
                )

        # 3. Fallback to single-source legacy behavior
        source = self._resolve_source(config, services)
        if source == "cts":
            return await self._execute_cts(config, execution, services)
        return await self._execute_recamera(config, execution, services)

    def _resolve_source(
        self,
        config: dict[str, Any],
        services: ServiceContainer,
    ) -> Literal["cts", "recamera"]:
        configured = str(config.get("source", self.DEFAULT_SOURCE))
        if configured == "auto":
            return "cts" if services.bucketizer is not None else "recamera"
        if configured == "cts":
            return "cts"
        if configured == "recamera":
            return "recamera"
        logger.warning("media_window_poll_invalid_source", source=configured)
        return "cts" if services.bucketizer is not None else "recamera"

    async def _execute_cts(
        self,
        config: dict[str, Any],
        execution: WorkflowExecution,
        services: ServiceContainer,
        cameras: list[str] | None = None,
    ) -> StepResult:
        now = datetime.now(UTC)
        lookback_s = float(config.get("lookback_s", 5))
        lookahead_s = float(config.get("lookahead_s", 5))
        window_start = now - timedelta(seconds=lookback_s)
        if cameras is None:
            cameras = list(config.get("cameras") or [])
        rooms: list[str] = list(config.get("rooms") or [])

        bucketizer = services.bucketizer
        if bucketizer is None:
            logger.warning(
                "media_window_poll_no_bucketizer",
                execution_id=str(execution.id),
            )
            return StepResult(
                data=self._empty_window(
                    execution=execution,
                    source="cts",
                    now=now,
                    window_start=window_start,
                    cameras=cameras,
                    rooms=rooms,
                )
            )

        collected = await collect_recent_cts_frames(
            bucketizer=bucketizer,
            minio_client=services.minio_client,
            config=CtsFrameWindowConfig(
                window_id=str(execution.id),
                cameras=cameras,
                rooms=rooms,
                lookback_s=lookback_s,
                lookahead_s=lookahead_s,
                sample_period_s=float(config.get("sample_period_s", 1.0)),
                max_frames=int(config.get("max_frames", 30)),
                now=now,
            ),
        )

        if bool(config.get("include_scene", False)):
            await _add_scene_captions(collected.frames, execution, services)

        summary = _summarize_frames(collected.frames)
        return StepResult(
            data={
                "trigger_id": execution.id,
                "window_start": window_start.isoformat(),
                "window_end": now.isoformat(),
                "cameras": collected.target_cameras,
                "rooms": summary["rooms"],
                "frames": collected.frames,
                "images": collected.images,
                "count": len(collected.images),
                "summary": summary,
                "source": "cts",
                "partial": collected.partial,
                "sensor_ids": [],
                "room_names": rooms,
                "since_minutes": 0,
                "polled_at": now.isoformat(),
            }
        )

    async def _execute_recamera(
        self,
        config: dict[str, Any],
        execution: WorkflowExecution,
        services: ServiceContainer,
        sensor_ids: list[str] | None = None,
    ) -> StepResult:
        now = datetime.now(UTC)
        since_minutes = float(config.get("since_minutes", 5))
        window_start = now - timedelta(minutes=since_minutes)
        if sensor_ids is None:
            sensor_ids = list(config.get("sensor_ids") or config.get("cameras") or [])
        room_names: list[str] = list(config.get("room_names") or config.get("rooms") or [])

        aggregator = services.event_aggregator
        if aggregator is None:
            logger.warning(
                "media_window_poll_no_event_aggregator",
                execution_id=str(execution.id),
            )
            return StepResult(
                data=self._empty_window(
                    execution=execution,
                    source="recamera",
                    now=now,
                    window_start=window_start,
                    cameras=sensor_ids,
                    rooms=room_names,
                    since_minutes=since_minutes,
                )
            )

        max_images = int(config.get("max_images", 10))
        if sensor_ids:
            images = await aggregator.query_media_by_sensor(
                sensor_ids_ordered=sensor_ids,
                images_per_sensor=int(config.get("images_per_sensor", 3)),
                sensor_frame_limits=config.get("sensor_frame_limits") or None,
                max_images=max_images,
                since_minutes=since_minutes,
                chronological=bool(config.get("chronological", True)),
            )
        else:
            images = await aggregator.query_recent_media(
                sensor_ids=None,
                room_names=room_names or None,
                limit=max_images,
                since_minutes=since_minutes,
            )

        logger.info(
            "media_window_poll_complete",
            execution_id=str(execution.id),
            source="recamera",
            count=len(images),
            sensor_ids=sensor_ids,
            room_names=room_names,
        )
        return StepResult(
            data={
                "trigger_id": execution.id,
                "window_start": window_start.isoformat(),
                "window_end": now.isoformat(),
                "cameras": sensor_ids,
                "rooms": room_names,
                "frames": [],
                "images": images,
                "count": len(images),
                "summary": {
                    "distinct_identities": [],
                    "detection_count": 0,
                    "rooms": room_names,
                },
                "source": "recamera",
                "partial": False,
                "sensor_ids": sensor_ids,
                "room_names": room_names,
                "since_minutes": since_minutes,
                "polled_at": now.isoformat(),
            }
        )

    async def _execute_mixed(
        self,
        config: dict[str, Any],
        execution: WorkflowExecution,
        resolved_cameras: list[ResolvedCamera],
        services: ServiceContainer,
    ) -> StepResult:
        now = datetime.now(UTC)
        lookback_s = float(config.get("lookback_s", 5))
        lookahead_s = float(config.get("lookahead_s", 5))
        window_start = now - timedelta(seconds=lookback_s)
        rooms: list[str] = list(config.get("rooms") or config.get("room_names") or [])

        collected = await collect_recent_frames_multi_source(
            bucketizer=services.bucketizer,
            event_aggregator=services.event_aggregator,
            minio_client=services.minio_client,
            db_factory=services.db_factory,
            cameras=resolved_cameras,
            rooms=rooms,
            lookback_s=lookback_s,
            lookahead_s=lookahead_s,
            sample_period_s=float(config.get("sample_period_s", 1.0)),
            max_frames=int(config.get("max_frames", 30)),
            now=now,
            since_minutes=config.get("since_minutes") or (lookback_s / 60.0),
            images_per_sensor=int(config.get("images_per_sensor", 3)),
        )

        if bool(config.get("include_scene", False)):
            await _add_scene_captions(collected["frames"], execution, services)

        summary = _summarize_frames(collected["frames"])

        sensor_ids = [c.id for c in resolved_cameras if c.source == "recamera"]

        return StepResult(
            data={
                "trigger_id": execution.id,
                "window_start": window_start.isoformat(),
                "window_end": now.isoformat(),
                "cameras": [c.id for c in resolved_cameras],
                "rooms": summary["rooms"] or rooms,
                "frames": collected["frames"],
                "images": collected["images"],
                "count": len(collected["images"]),
                "summary": summary,
                "source": "mixed",
                "partial": collected["partial"],
                "sensor_ids": sensor_ids,
                "room_names": rooms,
                "since_minutes": config.get("since_minutes") or (lookback_s / 60.0),
                "polled_at": now.isoformat(),
            }
        )

    @staticmethod
    def _empty_window(
        *,
        execution: WorkflowExecution,
        source: Literal["cts", "recamera"],
        now: datetime,
        window_start: datetime,
        cameras: list[str],
        rooms: list[str],
        since_minutes: float = 0,
    ) -> dict[str, Any]:
        return {
            "trigger_id": execution.id,
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "cameras": sorted(cameras),
            "rooms": sorted(rooms),
            "frames": [],
            "images": [],
            "count": 0,
            "summary": {
                "distinct_identities": [],
                "detection_count": 0,
                "rooms": sorted(rooms),
            },
            "source": source,
            "partial": True,
            "sensor_ids": cameras if source == "recamera" else [],
            "room_names": rooms,
            "since_minutes": since_minutes,
            "polled_at": now.isoformat(),
        }


def _parse_event_time(frame: dict[str, Any]) -> datetime | None:
    return parse_event_time(frame)


def _downsample_frames(
    frames: list[dict[str, Any]],
    *,
    sample_period_s: float,
    max_frames: int,
) -> list[dict[str, Any]]:
    downsampled: list[dict[str, Any]] = []
    last_kept: float | None = None
    for frame in frames:
        event_time = _parse_event_time(frame)
        if event_time is None:
            continue
        timestamp = event_time.timestamp()
        if last_kept is None or timestamp - last_kept >= sample_period_s:
            downsampled.append(frame)
            last_kept = timestamp
            if len(downsampled) >= max_frames:
                break
    return downsampled


def _summarize_frames(frames: list[dict[str, Any]]) -> dict[str, Any]:
    distinct_ids: set[str] = set()
    rooms_seen: set[str] = set()
    detection_count = 0
    for frame in frames:
        detections = frame.get("detections", [])
        detection_count += int(frame.get("detection_count", len(detections)))
        for detection in detections:
            identity_id = detection.get("identity_id", "")
            if identity_id:
                distinct_ids.add(identity_id)
        room = frame.get("room_name", "")
        if room:
            rooms_seen.add(room)
    return {
        "distinct_identities": sorted(distinct_ids),
        "detection_count": detection_count,
        "rooms": sorted(rooms_seen),
    }


async def _add_scene_captions(
    frames: list[dict[str, Any]],
    execution: WorkflowExecution,
    services: ServiceContainer,
) -> None:
    if services.scene_analysis_client is None or services.minio_client is None:
        logger.warning(
            "media_window_poll_scene_unavailable",
            execution_id=str(execution.id),
        )
        return
    for frame in frames:
        minio_key = frame.get("minio_key")
        if not minio_key:
            continue
        try:
            image_bytes = await services.minio_client.async_get_object(str(minio_key))
            if image_bytes is None:
                logger.warning(
                    "media_window_poll_scene_image_missing",
                    execution_id=str(execution.id),
                    minio_key=minio_key,
                )
                continue
            result = await services.scene_analysis_client.analyze(
                image_bytes,
                run_detect=False,
                run_describe=True,
                run_embed=False,
                run_hazards=False,
                sensor_id=str(frame.get("camera_id", "")),
            )
            description = getattr(result, "description", "")
            if description:
                frame["scene_caption"] = description
        except Exception:  # noqa: BLE001
            logger.warning(
                "media_window_poll_scene_failed",
                execution_id=str(execution.id),
                minio_key=minio_key,
                exc_info=True,
            )
