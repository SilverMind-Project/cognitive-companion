"""Read-only guided-task safety watch.

The watch owns perception conditions only: the resident left the step's room,
a hazard is visible, a no-motion or fall signal arrived, or she reported being
blocked repeatedly. Step timeouts and the attempts ladder belong to the state
machine's ``timeout_tick``; an idle check here would race it and defeat the
vision watch's nag suppression.

Conditions come in two kinds and are de-duplicated differently.

* Events (a fall or no-motion signal, repeated "stuck" reports) are new
  evidence. Each fires at most once per arm window and counts only evidence
  from inside it. A step is armed on entry and re-armed when a caregiver
  releases takeover.
* States (she is out of the step's room, a hazard is visible) last as long as
  they are true, so re-arming them would alert again for the same situation.
  Leaving the room alerts when it starts and again only after she has come
  back (recorded as a ``safety_condition_cleared`` observation) and left
  again; a release does not re-arm it, because the caregiver releasing has
  already seen it. A hazard is an emergency, so it is the exception: a release
  re-arms it, and a stove still on after the caregiver hands the session back
  alerts again.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.logging import get_logger
from backend.models.guided_task import RoutineStep
from backend.services.guided_task.camera_selection import (
    IdentityResolver,
    ResolvedCamera,
    select_cameras_tagged,
)
from backend.services.guided_task.store import GuidedTaskStore
from backend.services.media_window_frames import collect_recent_frames_multi_source

logger = get_logger(__name__)

_NO_MOTION_SIGNAL_KINDS = frozenset(
    {
        "stillness_anomaly",
        "fall_suspected",
        "inferred_dwell_exceeded",
    }
)

# D14 "repeated confusion/distress": the number of step_blocked reports in one
# arm window that trigger a caregiver-visible confusion_distress signal.
# Attempts-exhausted escalation belongs exclusively to the state machine's
# timeout_tick ladder; this threshold governs only the blocked-report signal.
_CONFUSION_DISTRESS_BLOCKED_THRESHOLD = 2

# Hazard frames: a short recent window from at most two cameras is enough to
# see a stove left on, and keeps the per-tick VLM cost bounded.
_HAZARD_MAX_CAMERAS = 2
_HAZARD_MAX_FRAMES = 3
_HAZARD_LOOKBACK_S = 10.0


class GuidedTaskSafetyWatch:
    """Evaluate guided-task safety conditions without mutating state."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        person_location_service: Any | None = None,
        zone_service: Any | None = None,
        bucketizer: Any | None = None,
        event_aggregator: Any | None = None,
        camera_source_resolver: Any | None = None,
        camera_topology: Any | None = None,
        identity_resolver: IdentityResolver | None = None,
        scene_analysis_client: Any | None = None,
        signals_service: Any | None = None,
        minio_client: Any | None = None,
        settings: Settings | None = None,
        time_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._store = GuidedTaskStore(db_factory)
        self._person_location_service = person_location_service
        self._zone_service = zone_service
        self._bucketizer = bucketizer
        self._event_aggregator = event_aggregator
        self._camera_source_resolver = camera_source_resolver
        self._camera_topology = camera_topology
        self._identity_resolver = identity_resolver
        self._scene_analysis_client = scene_analysis_client
        self._signals_service = signals_service
        self._minio_client = minio_client
        self._settings = settings or default_settings
        self._time_fn = time_fn or (lambda: datetime.now(UTC))

    async def evaluate(self, *, session: Any) -> list[dict]:
        """Return escalation events, plus cleared-state observations.

        An entry with ``"cleared": True`` is not an escalation: it records that a
        state condition which alerted has ended, and the caller writes it to the
        timeline as ``safety_condition_cleared``.
        """
        steps = self._store.list_steps(session.routine_id)
        step = _step_by_ord(steps, session.current_step_ord)
        if step is None:
            return []

        armed_at = self._armed_at(session, step)
        events: list[dict] = []

        def fresh(condition: str) -> bool:
            return not self._store.has_event(
                session_id=session.id,
                kind="safety_event",
                step_ord=step.ord,
                detail_condition=condition,
                since=armed_at,
            )

        # The raw room check also gates the hazard look below, so it is not
        # suppressed when the left-room alert itself already fired.
        left_expected_room = await self._left_expected_room(session, step)
        if left_expected_room is not None:
            episode_open = self._state_episode_open(session.id, step.ord, "left_expected_room")
            if left_expected_room and not episode_open:
                events.append(
                    {
                        "condition": "left_expected_room",
                        "severity": "high",
                        "detail": {"expected_zone_id": step.zone_id},
                    }
                )
            elif not left_expected_room and episode_open:
                events.append({"condition": "left_expected_room", "cleared": True})

        if fresh("no_motion"):
            no_motion = await self._no_motion_signal(session.person_id, since=armed_at)
            if no_motion is not None:
                events.append(
                    {
                        "condition": "no_motion",
                        "severity": "emergency",
                        "detail": no_motion,
                    }
                )

        blocked_count = self._store.count_events(
            session_id=session.id, kind="step_blocked", step_ord=step.ord, since=armed_at
        )
        if blocked_count >= _CONFUSION_DISTRESS_BLOCKED_THRESHOLD and fresh("confusion_distress"):
            events.append(
                {
                    "condition": "confusion_distress",
                    "severity": "high",
                    "detail": {
                        "attempts": session.attempts,
                        "blocked_count": blocked_count,
                    },
                }
            )

        if (left_expected_room or step.is_safety_critical) and fresh("hazard_active"):
            hazard = await self._hazard_event(session, step)
            if hazard is not None:
                events.append(hazard)

        for event in events:
            logger.info(
                "safety_condition_cleared" if event.get("cleared") else "safety_event",
                session_id=session.id,
                condition=event["condition"],
                severity=event.get("severity"),
            )
        return events

    def _state_episode_open(self, session_id: int, step_ord: int, condition: str) -> bool:
        """Whether ``condition`` alerted on this step and has not been seen to end."""
        fired_at = self._store.latest_event_at(
            session_id=session_id,
            kind="safety_event",
            step_ord=step_ord,
            detail_condition=condition,
        )
        if fired_at is None:
            return False
        cleared_at = self._store.latest_event_at(
            session_id=session_id,
            kind="safety_condition_cleared",
            step_ord=step_ord,
            detail_condition=condition,
        )
        return cleared_at is None or cleared_at < fired_at

    def _armed_at(self, session: Any, step: RoutineStep) -> datetime:
        """When the current step's conditions were last armed.

        Step entry, or a later caregiver release of takeover on this step.
        ``last_activity_at`` is deliberately not the anchor: every retry bumps
        it, which would hide a fall signal that arrived just before a retry.
        """
        candidates = [session.started_at]
        for kind in ("step_entered", "takeover_ended"):
            at = self._store.latest_event_at(session_id=session.id, kind=kind, step_ord=step.ord)
            if at is not None:
                candidates.append(at)
        return max(candidates)

    def _now(self) -> datetime:
        now = self._time_fn()
        if now.tzinfo is None:
            raise ValueError("GuidedTaskSafetyWatch time_fn must return timezone-aware datetimes")
        return now

    async def _left_expected_room(self, session: Any, step: RoutineStep) -> bool | None:
        """Whether she is outside the step's room; ``None`` when that is unknown.

        Unknown (no expected room, no location service, no current location) is
        kept apart from "in the room", so a gap in location data never closes an
        open left-room episode.
        """
        expected_room_id = self._expected_room_id(step)
        if expected_room_id is None or self._person_location_service is None:
            return None
        location = await self._person_location_service.where_is(session.person_id)
        if location is None:
            return None
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

    async def _no_motion_signal(self, person_id: str, *, since: datetime) -> dict | None:
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
            if kind not in _NO_MOTION_SIGNAL_KINDS:
                continue
            received_at = _parse_timestamp(signal.get("received_at"))
            # A signal from before the step was armed belongs to an earlier
            # moment; it must not raise a fresh fall emergency now. A signal
            # with no timestamp is kept, since dropping a real fall is worse.
            if received_at is not None and received_at < since:
                continue
            return signal
        return None

    async def _hazard_event(self, session: Any, step: RoutineStep) -> dict | None:
        if self._scene_analysis_client is None or self._minio_client is None:
            return None
        cameras: list[ResolvedCamera] = await select_cameras_tagged(
            person_id=session.person_id,
            step=step,
            zone_service=self._zone_service,
            person_location=self._person_location_service,
            bucketizer=self._bucketizer,
            event_aggregator=self._event_aggregator,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_resolver,
            camera_source_resolver=self._camera_source_resolver,
            max_cameras=_HAZARD_MAX_CAMERAS,
        )
        if not cameras:
            return None
        collected = await collect_recent_frames_multi_source(
            bucketizer=self._bucketizer,
            event_aggregator=self._event_aggregator,
            minio_client=self._minio_client,
            db_factory=self._db_factory,
            cameras=cameras,
            rooms=[],
            lookback_s=_HAZARD_LOOKBACK_S,
            lookahead_s=0.0,
            sample_period_s=1.0,
            max_frames=_HAZARD_MAX_FRAMES,
            now=self._now(),
        )
        for frame in collected.get("frames", []):
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
                        "cameras": [{"id": c.id, "source": c.source} for c in cameras],
                        "camera_id": str(frame.get("camera_id", "")),
                        "source": frame.get("source"),
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


def _parse_timestamp(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _step_by_ord(steps: list[RoutineStep], step_ord: int) -> RoutineStep | None:
    for step in steps:
        if step.ord == step_ord:
            return step
    return None
