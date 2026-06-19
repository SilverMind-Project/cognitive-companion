"""Shared CTS recent-frame collection for media-window consumers."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.logging import get_logger
from backend.services.guided_task.camera_selection import ResolvedCamera

logger = get_logger(__name__)


@dataclass(frozen=True)
class CtsFrameWindow:
    window_start: datetime
    window_end: datetime
    target_cameras: list[str]
    frames: list[dict[str, Any]]
    images: list[str]
    partial: bool = False


@dataclass(frozen=True)
class CtsFrameWindowConfig:
    window_id: str
    cameras: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    lookback_s: float = 5.0
    lookahead_s: float = 5.0
    sample_period_s: float = 1.0
    max_frames: int = 30
    now: datetime | None = None


async def collect_recent_cts_frames(
    *,
    bucketizer: Any | None,
    minio_client: Any | None,
    config: CtsFrameWindowConfig,
) -> CtsFrameWindow:
    """Collect recent CTS frames and presigned image URLs.

    This is the shared implementation used by ``media_window_poll`` and
    guided-task vision checks. It intentionally reads only the live CTS
    bucketizer and explicit room/camera filters; it does not consult camera
    visibility polygons.
    """
    now = config.now or datetime.now(UTC)
    window_start = now - timedelta(seconds=config.lookback_s)
    cameras = list(config.cameras)
    rooms = list(config.rooms)

    if bucketizer is None:
        return CtsFrameWindow(
            window_start=window_start,
            window_end=now,
            target_cameras=sorted(cameras),
            frames=[],
            images=[],
            partial=True,
        )

    target_cameras = cameras or sorted(bucketizer.buffer_stats())
    frames: list[dict[str, Any]] = []
    for camera_id in target_cameras:
        buffered = bucketizer.forward_buffer(
            window_id=config.window_id,
            camera_id=camera_id,
            lookahead_s=config.lookback_s + config.lookahead_s,
            eligible_only=True,
        )
        for frame in buffered:
            event_time = parse_event_time(frame)
            if event_time is None or event_time < window_start:
                continue
            if rooms and frame.get("room_name") not in rooms:
                continue
            frames.append(dict(frame))

    frames.sort(key=lambda frame: frame.get("event_time", ""))
    downsampled = downsample_frames(
        frames,
        sample_period_s=config.sample_period_s,
        max_frames=config.max_frames,
    )

    partial = False
    images: list[str] = []
    if minio_client is None and downsampled:
        partial = True
        logger.warning("cts_frame_window_no_minio_client")
    elif minio_client is not None:
        for frame in downsampled:
            minio_key = frame.get("minio_key")
            if not minio_key:
                continue
            try:
                images.append(
                    minio_client.generate_presigned_url(
                        str(minio_key),
                        expiration=3600,
                    )
                )
            except Exception:  # noqa: BLE001
                partial = True
                logger.warning(
                    "cts_frame_window_presign_failed",
                    camera_id=frame.get("camera_id"),
                    minio_key=minio_key,
                    exc_info=True,
                )

    return CtsFrameWindow(
        window_start=window_start,
        window_end=now,
        target_cameras=sorted(target_cameras),
        frames=downsampled,
        images=images,
        partial=partial,
    )


def parse_event_time(frame: dict[str, Any]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(frame["event_time"]))
    except ValueError, KeyError, TypeError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def downsample_frames(
    frames: list[dict[str, Any]],
    *,
    sample_period_s: float,
    max_frames: int,
) -> list[dict[str, Any]]:
    downsampled: list[dict[str, Any]] = []
    last_kept: float | None = None
    for frame in frames:
        event_time = parse_event_time(frame)
        if event_time is None:
            continue
        timestamp = event_time.timestamp()
        if last_kept is None or timestamp - last_kept >= sample_period_s:
            downsampled.append(frame)
            last_kept = timestamp
            if len(downsampled) >= max_frames:
                break
    return downsampled


async def collect_recent_frames_multi_source(
    *,
    bucketizer: Any | None,
    event_aggregator: Any | None,
    minio_client: Any | None,
    db_factory: Callable[[], Any] | None,
    cameras: list[ResolvedCamera],
    rooms: list[str],
    lookback_s: float,
    lookahead_s: float,
    sample_period_s: float,
    max_frames: int,
    now: datetime | None = None,
    since_minutes: float | None = None,
    images_per_sensor: int = 3,
) -> dict[str, Any]:
    """Collect recent frames and presigned image URLs from both CTS and reCamera.

    Orders them chronologically, applies the sample_period_s and max_frames downsample,
    and returns a unified payload matching the expected step result shape.
    """
    now = now or datetime.now(UTC)
    window_start = now - timedelta(seconds=lookback_s)

    cts_cameras = [c.id for c in cameras if c.source == "cts"]
    recamera_sensors = [c.id for c in cameras if c.source == "recamera"]

    cts_frames: list[dict[str, Any]] = []
    cts_partial = False

    if cts_cameras:
        if bucketizer is None:
            cts_partial = True
        else:
            target_cameras = cts_cameras
            for camera_id in target_cameras:
                buffered = bucketizer.forward_buffer(
                    window_id="multi_source_poll",
                    camera_id=camera_id,
                    lookahead_s=lookback_s + lookahead_s,
                    eligible_only=True,
                )
                for frame in buffered:
                    event_time = parse_event_time(frame)
                    if event_time is None or event_time < window_start:
                        continue
                    if rooms and frame.get("room_name") not in rooms:
                        continue
                    frame_copy = dict(frame)
                    frame_copy["source"] = "cts"
                    cts_frames.append(frame_copy)

    recamera_frames: list[dict[str, Any]] = []
    recamera_partial = False

    if recamera_sensors:
        if event_aggregator is None:
            recamera_partial = True
        else:
            query_since_min = since_minutes or (lookback_s / 60.0)
            images = await event_aggregator.query_media_by_sensor(
                sensor_ids_ordered=recamera_sensors,
                images_per_sensor=images_per_sensor,
                sensor_frame_limits=None,
                max_images=max_frames,
                since_minutes=query_since_min,
                chronological=True,
            )

            object_names = []
            for img in images:
                if minio_client is not None:
                    with contextlib.suppress(Exception):
                        object_names.append(minio_client.extract_object_name(img))

            db_rows = []
            if object_names and db_factory is not None:
                db = db_factory()
                try:
                    from backend.models.media_cache import MediaCache

                    db_rows = (
                        db.query(MediaCache).filter(MediaCache.object_name.in_(object_names)).all()
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("collect_recent_frames_recamera_db_failed", exc_info=True)
                finally:
                    if db is not None:
                        db.close()

            row_map = {r.object_name: r for r in db_rows}

            for i, url in enumerate(images):
                obj_name = None
                if minio_client is not None:
                    with contextlib.suppress(Exception):
                        obj_name = minio_client.extract_object_name(url)

                row = row_map.get(obj_name) if obj_name else None
                if row is not None:
                    captured_at = row.captured_at
                    if captured_at.tzinfo is None:
                        captured_at = captured_at.replace(tzinfo=UTC)
                    else:
                        captured_at = captured_at.astimezone(UTC)
                    sensor_id = row.sensor_id or ""
                else:
                    captured_at = None
                    sensor_id = ""
                    search_str = obj_name or url
                    if search_str:
                        import re

                        ts_match = re.search(r"(\d{8})_(\d{6})", search_str)
                        if ts_match:
                            with contextlib.suppress(Exception):
                                captured_at = datetime.strptime(
                                    ts_match.group(0), "%Y%m%d_%H%M%S"
                                ).replace(tzinfo=UTC)
                        else:
                            num_match = re.search(r"(\d+(\.\d+)?)", search_str)
                            if num_match:
                                with contextlib.suppress(Exception):
                                    seconds_ago = float(num_match.group(1))
                                    captured_at = now - timedelta(seconds=seconds_ago)
                    if captured_at is None:
                        captured_at = now - timedelta(seconds=i * 2.0)
                    sensor_id = recamera_sensors[0] if recamera_sensors else "recamera"

                recamera_frames.append(
                    {
                        "camera_id": sensor_id,
                        "event_time": captured_at.isoformat(),
                        "room_name": "",
                        "detections": [],
                        "detection_count": 0,
                        "minio_key": obj_name or url,
                        "image_eligible": True,
                        "presigned_url": url,
                        "source": "recamera",
                    }
                )

    merged_frames = cts_frames + recamera_frames
    merged_frames.sort(key=lambda f: f.get("event_time", ""))

    downsampled = downsample_frames(
        merged_frames,
        sample_period_s=sample_period_s,
        max_frames=max_frames,
    )

    final_images = []
    for frame in downsampled:
        if frame.get("source") == "cts":
            mkey = frame.get("minio_key")
            if mkey and minio_client is not None:
                try:
                    url = minio_client.generate_presigned_url(
                        str(mkey),
                        expiration=3600,
                    )
                    final_images.append(url)
                except Exception:  # noqa: BLE001
                    cts_partial = True
                    logger.warning("cts_frame_window_presign_failed", minio_key=mkey, exc_info=True)
            else:
                if minio_client is None:
                    cts_partial = True
        else:
            final_images.append(frame["presigned_url"])

    # Determine unified source value
    has_cts = any(c.source == "cts" for c in cameras)
    has_recamera = any(c.source == "recamera" for c in cameras)
    if has_cts and has_recamera:
        unified_source = "mixed"
    elif has_recamera:
        unified_source = "recamera"
    else:
        unified_source = "cts"

    return {
        "window_start": window_start,
        "window_end": now,
        "target_cameras": [c.id for c in cameras],
        "frames": downsampled,
        "images": final_images,
        "partial": cts_partial or recamera_partial,
        "source": unified_source,
    }
