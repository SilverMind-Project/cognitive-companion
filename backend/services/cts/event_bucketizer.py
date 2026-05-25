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
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger

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
    ) -> None:
        self._pipeline = pipeline
        self._get_triggers = get_triggers
        self._cfg = config or BucketizerConfig()
        # camera_id -> deque of (event_time_iso, event_dict)
        self._buffers: dict[str, deque[tuple[str, dict[str, Any]]]] = defaultdict(
            lambda: deque(maxlen=self._cfg.max_buffer_per_camera)
        )
        # trigger_id -> float (last fire monotonic seconds)
        self._last_fire: dict[str, float] = {}

    def ingest(self, event: dict[str, Any]) -> None:
        """Feed one tracking event into the bucketizer.

        Called by ``TrackingEventSubscriber`` after the WS broadcast.
        """
        camera_id = event.get("camera_id", "unknown")
        event_time = event.get("event_time", "")

        self._buffers[camera_id].append((event_time, event))

        triggers = self._get_triggers() if self._get_triggers else []
        self._evaluate_triggers(triggers, camera_id)

    def forward_buffer(
        self,
        window_id: str,
        camera_id: str,
        lookahead_s: float,
    ) -> list[dict[str, Any]]:
        """Return a snapshot of recent events for *camera_id* for use by
        the ``cts_window_poll`` step's lookahead path."""
        # Return all buffered events for this camera.
        # A production version would filter by timestamp / lookahead_s.
        _ = lookahead_s  # reserved for future timestamp filtering
        return [evt for _ts, evt in self._buffers[camera_id]]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evaluate_triggers(
        self,
        triggers: list[CtsWindowTrigger],
        camera_id: str,
    ) -> None:
        """Check every enabled trigger whose camera/room filter matches."""
        now = time.monotonic()
        for trigger in triggers:
            if not trigger.enabled:
                continue
            if trigger.cameras and camera_id not in trigger.cameras:
                continue
            # Check cooldown.
            last = self._last_fire.get(trigger.id)
            if last is not None and (now - last) < trigger.cooldown_seconds:
                continue
            if self._trigger_should_fire(trigger):
                self._last_fire[trigger.id] = now
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
        return {cam: len(buf) for cam, buf in self._buffers.items()}
