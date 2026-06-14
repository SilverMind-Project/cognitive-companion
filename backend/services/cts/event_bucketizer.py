"""CtsEventBucketizer: in-memory sliding-window aggregator for CTS frames.

Maintains per-camera ``collections.deque`` buffers of recent TrackingEvent
dicts and evaluates ``CtsWindowTrigger`` rules on each ingest. When a
trigger's thresholds are met, it fires a ``cts_window`` pipeline event
with the full buffer payload.

This is a CC-side service fed by ``TrackingEventSubscriber`` — there is
no new Redis stream and no orchestrator-side change. The bucketizer
shares the same consumer-group subscription point as the live-view path.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.logging import get_logger
from backend.observability.aggregation_metrics import aggregator_images_dropped
from backend.services.aggregation import (
    CameraBufferState,
    CooldownTracker,
    PerCameraRateLimiter,
)

logger = get_logger(__name__)


@dataclass
class CtsWindowTrigger:
    """In-memory snapshot of a persisted ``CtsWindowTrigger`` row.

    Loaded at startup and refreshed periodically so rule changes take
    effect without a restart.
    """

    id: str
    name: str
    window_seconds: float
    min_detections: int
    min_identities: int
    cameras: list[str] | None = None
    rooms: list[str] | None = None
    cooldown_seconds: float = 0.0
    enabled: bool = True


@dataclass
class BucketizerConfig:
    """Configuration for the CtsEventBucketizer."""

    max_buffer_per_camera: int = 512


class BucketizerRateConfig(BaseModel):
    """Validated per-camera image ceiling for the CTS bucketizer."""

    model_config = ConfigDict(extra="forbid")

    image_rate_per_second: float = Field(default=0.5, ge=0.0)
    image_rate_burst: float = Field(default=2.0, ge=0.0)
    image_rate_overrides: dict[str, float] = Field(default_factory=dict)

    @field_validator("image_rate_overrides")
    @classmethod
    def validate_overrides(cls, overrides: dict[str, float]) -> dict[str, float]:
        if any(rate < 0.0 for rate in overrides.values()):
            raise ValueError("image rate overrides must be non-negative")
        return overrides


class CtsEventBucketizer:
    """Sliding-window bucketizer that fires ``cts_window`` pipeline events.

    Usage::

        bucketizer = CtsEventBucketizer(
            pipeline=cc_pipeline,
            get_triggers=load_triggers_fn,
        )
        # On each TrackingEvent:
        bucketizer.ingest(event_dict)
    """

    def __init__(
        self,
        *,
        pipeline: Any = None,
        get_triggers: Any = None,
        config: BucketizerConfig | None = None,
        rate_config: BucketizerRateConfig | dict[str, Any] | None = None,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pipeline = pipeline
        self._get_triggers = get_triggers
        self._cfg = config or BucketizerConfig()
        self._rate_cfg = (
            rate_config
            if isinstance(rate_config, BucketizerRateConfig)
            else BucketizerRateConfig.model_validate(rate_config or {})
        )
        # camera_id -> deque of (event_time_iso, event_dict)
        self._buffers: dict[str, deque[tuple[str, dict[str, Any]]]] = defaultdict(
            lambda: deque(maxlen=self._cfg.max_buffer_per_camera)
        )
        self._cooldowns = CooldownTracker(time_fn=time_fn)
        self._rate_limiter = PerCameraRateLimiter(
            default_rate_per_second=self._rate_cfg.image_rate_per_second,
            default_burst=self._rate_cfg.image_rate_burst or None,
            time_fn=time_fn,
        )
        for camera_id, rate in self._rate_cfg.image_rate_overrides.items():
            self._rate_limiter.set_camera_rate(camera_id, rate)
        self._eligible_counts: dict[str, int] = defaultdict(int)
        self._dropped_counts: dict[str, int] = defaultdict(int)

    def ingest(self, event: dict[str, Any]) -> None:
        """Feed one tracking event into the bucketizer.

        Called by ``TrackingEventSubscriber`` after the WS broadcast.
        """
        camera_id = event.get("camera_id", "unknown")
        event_time = event.get("event_time", "")

        self._buffers[camera_id].append((event_time, event))

        if event.get("minio_key"):
            if self._rate_limiter.allow(camera_id):
                event["image_eligible"] = True
                self._eligible_counts[camera_id] += 1
            else:
                event["image_eligible"] = False
                self._dropped_counts[camera_id] += 1
                aggregator_images_dropped.labels(camera_id=camera_id, origin="cts").inc()
                logger.debug(
                    "cts_image_rate_limited",
                    camera_id=camera_id,
                    rate_per_second=self._rate_limiter.rate_for(camera_id),
                )
        else:
            event["image_eligible"] = False

        triggers = self._get_triggers() if self._get_triggers else []
        self._evaluate_triggers(triggers, camera_id)

    def forward_buffer(
        self,
        window_id: str,
        camera_id: str,
        lookahead_s: float,
        eligible_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Return a snapshot of recent events for *camera_id* for use by
        the ``cts_window_poll`` step's lookahead path."""
        # Return all buffered events for this camera.
        # A production version would filter by timestamp / lookahead_s.
        _ = lookahead_s  # reserved for future timestamp filtering
        events = [evt for _ts, evt in self._buffers[camera_id]]
        if eligible_only:
            return [event for event in events if event.get("image_eligible")]
        return events

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evaluate_triggers(
        self,
        triggers: list[CtsWindowTrigger],
        camera_id: str,
    ) -> None:
        """Check every enabled trigger whose camera/room filter matches."""
        for trigger in triggers:
            if not trigger.enabled:
                continue
            if trigger.cameras and camera_id not in trigger.cameras:
                continue
            # Check cooldown.
            if self._cooldowns.active(trigger.id):
                continue
            if self._trigger_should_fire(trigger):
                self._cooldowns.arm(trigger.id, trigger.cooldown_seconds)
                self._fire(trigger)

    def _trigger_should_fire(self, trigger: CtsWindowTrigger) -> bool:
        """Return True if *trigger* thresholds are met given current buffers."""
        cutoff = datetime.now(UTC).timestamp() - trigger.window_seconds
        frames: list[dict[str, Any]] = []
        # Collect frames within the window across relevant cameras.
        cameras = trigger.cameras or list(self._buffers.keys())
        for cam_id in cameras:
            buf = self._buffers.get(cam_id)
            if buf is None:
                continue
            for ts_str, evt in buf:
                try:
                    evt_ts = datetime.fromisoformat(ts_str).timestamp()
                except ValueError, TypeError:
                    continue
                if evt_ts >= cutoff:
                    if trigger.rooms:
                        room = evt.get("room_name", "")
                        if room not in trigger.rooms:
                            continue
                    frames.append(evt)

        if len(frames) < trigger.min_detections:
            return False

        if trigger.min_identities > 0:
            unique_ids: set[str] = set()
            for f in frames:
                for det in f.get("detections", []):
                    iid = det.get("identity_id", "")
                    if iid:
                        unique_ids.add(iid)
            if len(unique_ids) < trigger.min_identities:
                return False

        return True

    def _fire(self, trigger: CtsWindowTrigger) -> None:
        """Fire a ``cts_window`` pipeline event for *trigger*."""
        if self._pipeline is None:
            return
        cutoff = datetime.now(UTC).timestamp() - trigger.window_seconds
        cameras = trigger.cameras or list(self._buffers.keys())
        frames: list[dict[str, Any]] = []
        distinct_ids: set[str] = set()
        rooms_seen: set[str] = set()
        detection_count = 0

        for cam_id in cameras:
            buf = self._buffers.get(cam_id)
            if buf is None:
                continue
            for ts_str, evt in buf:
                try:
                    evt_ts = datetime.fromisoformat(ts_str).timestamp()
                except ValueError, TypeError:
                    continue
                if evt_ts >= cutoff:
                    frames.append(evt)
                    detection_count += evt.get("detection_count", len(evt.get("detections", [])))
                    for det in evt.get("detections", []):
                        iid = det.get("identity_id", "")
                        if iid:
                            distinct_ids.add(iid)
                    room = evt.get("room_name", "")
                    if room:
                        rooms_seen.add(room)

        frames.sort(key=lambda f: f.get("event_time", ""))

        payload = {
            "trigger_id": trigger.id,
            "window_start": datetime.fromtimestamp(cutoff, tz=UTC).isoformat(),
            "window_end": datetime.now(UTC).isoformat(),
            "cameras": sorted(cameras),
            "rooms": sorted(rooms_seen),
            "frames": frames,
            "summary": {
                "distinct_identities": sorted(distinct_ids),
                "detection_count": detection_count,
                "rooms": sorted(rooms_seen),
            },
        }

        import asyncio

        async def _fire():
            try:
                await self._pipeline.fire_event(
                    source="cts",
                    kind="cts_window",
                    payload=payload,
                )
            except Exception:
                logger.exception(
                    "cts_window_bucketizer_fire_error",
                    trigger_id=trigger.id,
                    trigger_name=trigger.name,
                )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_fire(), name=f"cts_window_fire_{trigger.id}")  # noqa: RUF006
        except RuntimeError:
            logger.warning(
                "cts_window_bucketizer_no_event_loop",
                trigger_id=trigger.id,
            )

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def buffer_stats(self) -> dict[str, int]:
        """Return per-camera buffer sizes for diagnostics."""
        return {state.camera_id: state.buffer_depth for state in self.buffer_state()}

    def buffer_state(self) -> list[CameraBufferState]:
        """Return a uniform snapshot of active CTS camera buffers."""
        return [
            CameraBufferState(
                camera_id=camera_id,
                origin="cts",
                buffer_depth=len(buffer),
                buffer_capacity=self._cfg.max_buffer_per_camera,
                rate_per_second=self._rate_limiter.rate_for(camera_id),
                tokens_available=self._rate_limiter.tokens_available(camera_id),
                images_eligible_total=self._eligible_counts[camera_id],
                images_dropped_total=self._dropped_counts[camera_id],
                last_event_at=buffer[-1][0] if buffer else None,
            )
            for camera_id, buffer in self._buffers.items()
        ]
