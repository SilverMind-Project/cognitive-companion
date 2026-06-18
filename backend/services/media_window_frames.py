"""Shared CTS recent-frame collection for media-window consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.logging import get_logger

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
