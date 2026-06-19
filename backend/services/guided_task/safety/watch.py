"""Read-only guided-task safety watch."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.logging import get_logger
from backend.models.guided_task import RoutineStep
from backend.services.guided_task.camera_selection import IdentityResolver, select_cameras
from backend.services.guided_task.policy import resolve_policy
from backend.services.guided_task.store import GuidedTaskStore
from backend.services.media_window_frames import CtsFrameWindowConfig, collect_recent_cts_frames

logger = get_logger(__name__)

_NO_MOTION_SIGNAL_KINDS = frozenset(
    {
        "stillness_anomaly",
        "fall_suspected",
        "inferred_dwell_exceeded",
        "prolonged_stillness",
    }
)


class GuidedTaskSafetyWatch:
    """Evaluate M7 guided-task safety conditions without mutating state."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        person_location_service: Any | None = None,
        zone_service: Any | None = None,
        bucketizer: Any | None = None,
        camera_topology: Any | None = None,
        identity_resolver: IdentityResolver | None = None,
        scene_analysis_client: Any | None = None,
        signals_service: Any | None = None,
        minio_client: Any | None = None,
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = GuidedTaskStore(db_factory)
        self._person_location_service = person_location_service
        self._zone_service = zone_service
        self._bucketizer = bucketizer
        self._camera_topology = camera_topology
        self._identity_resolver = identity_resolver
        self._scene_analysis_client = scene_analysis_client
        self._signals_service = signals_service
        self._minio_client = minio_client
        self._settings = settings or default_settings
        self._time_fn = time_fn or (lambda: datetime.now(UTC))

    async def evaluate(self, *, session: Any) -> list[dict]:
        routine = self._store.get_routine(session.routine_id)
        steps = self._store.list_steps(session.routine_id)
        if routine is None or not steps:
            return []
        step = _step_by_ord(steps, session.current_step_ord)
        if step is None:
            return []

        policy = resolve_policy(routine, step, self._settings)
        now = self._now()
        events: list[dict] = []

        left_expected_room = await self._left_expected_room(session, step)
        if left_expected_room:
            events.append(
                {
                    "condition": "abandoned",
                    "severity": "high",
                    "detail": {"reason": "left_expected_room"},
                }
            )

        idle_s = (now - session.last_activity_at).total_seconds()
        if idle_s > policy.step_timeout_s:
            events.append(
                {
                    "condition": "abandoned",
                    "severity": "high",
                    "detail": {"reason": "idle_timeout", "idle_s": idle_s},
                }
            )

        no_motion = await self._no_motion_signal(session.person_id)
        if no_motion is not None:
            events.append(
                {
                    "condition": "no_motion",
                    "severity": "emergency",
                    "detail": no_motion,
                }
            )

        if (
            session.attempts >= max(0, policy.max_step_attempts - 1)
            or self._blocked_count(session) >= 2
        ):
            events.append(
                {
                    "condition": "confusion_distress",
                    "severity": "high",
                    "detail": {
                        "attempts": session.attempts,
                        "blocked_count": self._blocked_count(session),
                    },
                }
            )

        if left_expected_room or step.is_safety_critical:
            hazard = await self._hazard_event(session, step)
            if hazard is not None:
                events.append(hazard)

        for event in events:
            logger.info(
                "safety_event",
                session_id=session.id,
                condition=event["condition"],
                severity=event["severity"],
            )
        return events

    def _now(self) -> datetime:
        now = self._time_fn()
        if now.tzinfo is None:
            raise ValueError("GuidedTaskSafetyWatch time_fn must return timezone-aware datetimes")
        return now

    async def _left_expected_room(self, session: Any, step: RoutineStep) -> bool:
        expected_room_id = self._expected_room_id(step)
        if expected_room_id is None or self._person_location_service is None:
            return False
        location = await self._person_location_service.where_is(session.person_id)
        if location is None:
            return False
        return getattr(location, "room_id", None) != expected_room_id

    def _expected_room_id(self, step: RoutineStep) -> int | None:
        if step.zone_id is None or self._zone_service is None:
            return None
        try:
            zone = self._zone_service.get_zone(step.zone_id)
        except Exception:  # noqa: BLE001
            logger.warning("guided_safety_expected_zone_unavailable", zone_id=step.zone_id)
            return None
        room_id = getattr(zone, "room_id", None)
        return int(room_id) if room_id is not None else None

    async def _no_motion_signal(self, person_id: str) -> dict | None:
        signals = self._signals_service
        if signals is None:
            return None
        recent = await signals.list_recent(
            person_id=person_id,
            signal_kind=None,
            severity_min="warning",
            window_minutes=10,
            limit=10,
        )
        for signal in recent:
            kind = str(signal.get("signal_type") or signal.get("kind") or "")
            if kind in _NO_MOTION_SIGNAL_KINDS:
                return signal
        return None

    def _blocked_count(self, session: Any) -> int:
        return self._store.count_events(session_id=session.id, kind="step_blocked")

    async def _hazard_event(self, session: Any, step: RoutineStep) -> dict | None:
        if (
            self._scene_analysis_client is None
            or self._bucketizer is None
            or self._minio_client is None
        ):
            return None
        cameras = await select_cameras(
            person_id=session.person_id,
            step=step,
            zone_service=self._zone_service,
            person_location=self._person_location_service,
            bucketizer=self._bucketizer,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_resolver,
            max_cameras=2,
        )
        if not cameras:
            return None
        collected = await collect_recent_cts_frames(
            bucketizer=self._bucketizer,
            minio_client=self._minio_client,
            config=CtsFrameWindowConfig(
                window_id=f"guided_safety_{session.id}_{step.ord}",
                cameras=cameras,
                lookback_s=10.0,
                lookahead_s=0.0,
                sample_period_s=1.0,
                max_frames=3,
                now=self._now(),
            ),
        )
        for frame in collected.frames:
            minio_key = frame.get("minio_key")
            if not minio_key:
                continue
            image_bytes = await self._minio_client.async_get_object(str(minio_key))
            if image_bytes is None:
                continue
            result = await self._scene_analysis_client.analyze(
                image_bytes,
                run_detect=True,
                run_describe=False,
                run_embed=False,
                run_hazards=True,
                sensor_id=str(frame.get("camera_id", "")),
            )
            hazards = list(getattr(result, "hazards", []) or [])
            if hazards:
                return {
                    "condition": "hazard_active",
                    "severity": "emergency",
                    "detail": {
                        "cameras": cameras,
                        "hazards": [
                            {
                                "name": getattr(hazard, "name", ""),
                                "severity": getattr(hazard, "severity", ""),
                                "description": getattr(hazard, "description", ""),
                            }
                            for hazard in hazards
                        ],
                    },
                }
        return None


def _step_by_ord(steps: list[RoutineStep], step_ord: int) -> RoutineStep | None:
    for step in steps:
        if step.ord == step_ord:
            return step
    return None
