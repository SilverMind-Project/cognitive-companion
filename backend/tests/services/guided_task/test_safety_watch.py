from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.room_zone import RoomZone
from backend.services.cts.signal_config import ALL_SIGNAL_KINDS
from backend.services.guided_task.safety import GuidedTaskSafetyWatch
from backend.services.guided_task.safety.watch import _NO_MOTION_SIGNAL_KINDS
from backend.services.guided_task.service import GuidedTaskService
from backend.services.guided_task.store import GuidedTaskStore


@dataclass
class _Clock:
    now: datetime = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _Location:
    room_id: int
    room_name: str = "kitchen"


@dataclass
class _Zone:
    id: int
    room_id: int


class _LocationService:
    def __init__(self, room_id: int) -> None:
        self.room_id = room_id

    async def where_is(self, person_id: str) -> _Location:
        return _Location(room_id=self.room_id)


class _ZoneService:
    def __init__(self, room_id: int = 1) -> None:
        self.room_id = room_id

    def get_zone(self, zone_id: int) -> _Zone:
        return _Zone(id=zone_id, room_id=self.room_id)

    def cameras_for_zone(self, zone_id: int) -> list[str]:
        return ["cam-1"]


class _Signals:
    async def list_recent(self, **kwargs):
        return [{"signal_type": "stillness_anomaly", "severity": "emergency"}]


class _Bucketizer:
    def buffer_stats(self) -> dict[str, int]:
        return {"cam-1": 1}

    def forward_buffer(self, window_id, camera_id, lookahead_s, eligible_only=False):
        return [
            {
                "camera_id": camera_id,
                "event_time": datetime.now(UTC).isoformat(),
                "detections": [{"identity_id": "resident-1"}],
                "minio_key": "frames/cam-1.jpg",
                "image_eligible": True,
            }
        ]


class _Minio:
    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> str:
        return f"https://minio/{object_name}"

    async def async_get_object(self, object_name: str) -> bytes:
        return b"image"


@dataclass
class _Hazard:
    name: str = "stove_on"
    severity: str = "emergency"
    description: str = "Stove appears active"


class _Scene:
    def __init__(self, hazards: list[_Hazard] | None = None) -> None:
        self.hazards = hazards or []
        self.calls = 0

    async def analyze(self, *args, **kwargs):
        self.calls += 1
        return type("_Result", (), {"hazards": self.hazards})()


def _settings(max_attempts: int = 3, step_timeout_s: int = 300) -> Settings:
    return Settings.from_dict(
        {
            "guided_task": {
                "step_timeout_s": step_timeout_s,
                "max_step_attempts": max_attempts,
                "resume_grace_s": 600,
            }
        }
    )


def _seed(db_session, *, safety_critical: bool = False, attempts: int = 0) -> int:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    room = Room(name="Kitchen")
    db_session.add(room)
    db_session.flush()
    zone = RoomZone(
        room_id=room.id,
        name="Sink",
        polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
        camera_ids=["cam-1"],
    )
    db_session.add(zone)
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Step",
            completion_gate={"kinds": ["response"]},
            zone_id=zone.id,
            is_safety_critical=safety_critical,
        )
    )
    db_session.flush()
    session = GuidedSession(
        routine_id=routine.id,
        person_id="resident-1",
        status="active",
        current_step_ord=0,
        attempts=attempts,
        started_at=now,
        last_activity_at=now,
    )
    db_session.add(session)
    db_session.commit()
    return session.id


def _watch(db_factory, clock: _Clock, **kwargs) -> GuidedTaskSafetyWatch:
    return GuidedTaskSafetyWatch(
        db_factory=db_factory,
        settings=kwargs.pop("settings", _settings()),
        time_fn=clock,
        **kwargs,
    )


async def test_wandered_off_emits_high(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    watch = _watch(
        db_factory,
        _Clock(),
        person_location_service=_LocationService(room_id=2),
        zone_service=_ZoneService(room_id=1),
    )

    events = await watch.evaluate(session=session)

    assert [event["condition"] for event in events] == ["left_expected_room"]
    assert events[0]["severity"] == "high"


async def test_idle_beyond_timeout_is_not_a_safety_event(db_session, db_factory) -> None:
    """Idle time belongs to the state machine's timeout ladder. The watch used to
    emit an "abandoned" event here, racing the ladder and escalating a step the
    vision watch had just marked as making progress (nag suppression)."""
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    clock = _Clock(now=session.last_activity_at + timedelta(seconds=3000))
    watch = _watch(db_factory, clock, settings=_settings(step_timeout_s=300))

    assert await watch.evaluate(session=session) == []


async def test_hazard_emits_emergency(db_session, db_factory) -> None:
    session_id = _seed(db_session, safety_critical=True)
    session = db_session.get(GuidedSession, session_id)
    watch = _watch(
        db_factory,
        _Clock(),
        bucketizer=_Bucketizer(),
        identity_resolver=lambda _person_id: {"resident-1"},
        scene_analysis_client=_Scene([_Hazard()]),
        minio_client=_Minio(),
    )

    events = await watch.evaluate(session=session)

    assert any(
        event["condition"] == "hazard_active" and event["severity"] == "emergency"
        for event in events
    )


async def test_no_motion_signal_emits_emergency(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    watch = _watch(db_factory, _Clock(), signals_service=_Signals())

    events = await watch.evaluate(session=session)

    assert any(
        event["condition"] == "no_motion" and event["severity"] == "emergency" for event in events
    )


async def test_attempts_do_not_trigger_safety_escalation(db_session, db_factory) -> None:
    """G8: the attempts ladder belongs exclusively to the state machine's
    timeout_tick; the safety watch must not preempt it from attempts alone."""
    session_id = _seed(db_session, attempts=2)
    session = db_session.get(GuidedSession, session_id)
    watch = _watch(db_factory, _Clock(), settings=_settings(max_attempts=3))

    events = await watch.evaluate(session=session)

    assert not any(event["condition"] == "confusion_distress" for event in events)


async def test_blocked_reports_escalate_once(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    store = GuidedTaskStore(db_factory)
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    for _ in range(2):
        store.add_event(
            session_id=session_id, at=now, kind="step_blocked", step_ord=0, actor="system"
        )
    watch = _watch(db_factory, _Clock())

    first = await watch.evaluate(session=session)
    assert any(
        event["condition"] == "confusion_distress" and event["severity"] == "high"
        for event in first
    )

    # Persist the safety_event the same way GuidedTaskService._apply_decision
    # would after the first tick, then re-evaluate: the second tick must not
    # re-emit for the same (session, step_ord).
    store.add_event(
        session_id=session_id,
        at=now,
        kind="safety_event",
        step_ord=0,
        actor="system",
        detail={"condition": "confusion_distress", "severity": "high"},
    )
    second = await watch.evaluate(session=session)
    assert not any(event["condition"] == "confusion_distress" for event in second)


def test_no_motion_signal_kinds_are_canonical() -> None:
    """G14: guard against a future CTS signal-kind rename silently orphaning
    the watch's no-motion subscription."""
    assert set(ALL_SIGNAL_KINDS) >= _NO_MOTION_SIGNAL_KINDS


class _RecordingEscalator:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, bool]] = []

    async def escalate(self, *, session, reason: str, emergency: bool) -> None:
        self.calls.append((session.id, reason, emergency))


def _seed_service_routine(db_session) -> int:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Pour water.",
            completion_gate={"kinds": ["response"]},
        )
    )
    db_session.commit()
    return routine.id


async def test_third_attempt_window_runs_to_completion(db_session, db_factory) -> None:
    """G8 regression: with max_step_attempts=3, the full third attempt window
    elapses before any escalation, and the timeout ladder and the safety
    watch cannot double-escalate for the same cause."""
    routine_id = _seed_service_routine(db_session)
    clock = _Clock()
    escalator = _RecordingEscalator()
    settings = _settings(max_attempts=3, step_timeout_s=300)
    safety_watch = GuidedTaskSafetyWatch(db_factory=db_factory, settings=settings, time_fn=clock)
    service = GuidedTaskService(
        db_factory=db_factory,
        escalator=escalator,
        safety_watch=safety_watch,
        settings=settings,
        time_fn=clock,
    )
    session = await service.start(routine_id, "resident-1")

    clock.now += timedelta(seconds=300)
    first = await service.on_step_timeout(session.id)
    assert first.kind == "retry"

    clock.now += timedelta(seconds=300)
    second = await service.on_step_timeout(session.id)
    assert second.kind == "retry"

    # 20 seconds into the third (final) attempt window: a safety tick must
    # not preempt the state machine's timeout ladder.
    clock.now += timedelta(seconds=20)
    await service.tick(clock.now)
    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).status == "active"
    assert escalator.calls == []

    # Let the rest of the third window elapse; only the timeout ladder
    # escalates, and it does so exactly once.
    clock.now += timedelta(seconds=280)
    third = await service.on_step_timeout(session.id)

    assert third.kind == "escalate"
    assert escalator.calls == [(session.id, "attempts_exhausted", False)]


async def test_hazard_vlm_not_run_when_no_risk_signals(db_session, db_factory) -> None:
    session_id = _seed(db_session, safety_critical=False)
    session = db_session.get(GuidedSession, session_id)
    scene = _Scene([_Hazard()])
    watch = _watch(
        db_factory,
        _Clock(),
        person_location_service=_LocationService(room_id=1),
        zone_service=_ZoneService(room_id=1),
        bucketizer=_Bucketizer(),
        scene_analysis_client=scene,
        minio_client=_Minio(),
    )

    events = await watch.evaluate(session=session)

    assert scene.calls == 0
    assert not any(event["condition"] == "hazard_active" for event in events)


async def test_watch_does_not_change_step_state(db_session, db_factory) -> None:
    session_id = _seed(db_session, attempts=2)
    session = db_session.get(GuidedSession, session_id)
    watch = _watch(db_factory, _Clock(), settings=_settings(max_attempts=3))

    await watch.evaluate(session=session)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session_id)
    assert stored.status == "active"
    assert stored.current_step_ord == 0
    assert stored.attempts == 2


async def test_missing_perception_services_graceful(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    watch = _watch(db_factory, _Clock())

    assert await watch.evaluate(session=session) == []


# ---------------------------------------------------------------------------
# Arming: each condition fires once per step, re-armed by a caregiver release
# ---------------------------------------------------------------------------


def _record_safety_event(db_factory, session_id: int, condition: str, at: datetime) -> None:
    GuidedTaskStore(db_factory).add_event(
        session_id=session_id,
        at=at,
        kind="safety_event",
        step_ord=0,
        actor="system",
        detail={"condition": condition, "severity": "high"},
    )


class _TimedSignals:
    def __init__(self, received_at: datetime) -> None:
        self.received_at = received_at

    async def list_recent(self, **kwargs):
        return [
            {
                "signal_type": "fall_suspected",
                "severity": "emergency",
                "received_at": self.received_at.isoformat(),
            }
        ]


async def test_conditions_fire_once_per_step_then_rearm_on_release(db_session, db_factory) -> None:
    session_id = _seed(db_session, safety_critical=True)
    session = db_session.get(GuidedSession, session_id)
    clock = _Clock(now=session.started_at + timedelta(seconds=60))
    watch = _watch(
        db_factory,
        clock,
        person_location_service=_LocationService(room_id=2),
        zone_service=_ZoneService(room_id=1),
        signals_service=_TimedSignals(session.started_at + timedelta(seconds=30)),
        bucketizer=_Bucketizer(),
        scene_analysis_client=_Scene([_Hazard()]),
        minio_client=_Minio(),
    )

    first = {event["condition"] for event in await watch.evaluate(session=session)}
    assert first == {"left_expected_room", "no_motion", "hazard_active"}
    for condition in first:
        _record_safety_event(db_factory, session_id, condition, clock.now)

    clock.now += timedelta(seconds=20)
    assert await watch.evaluate(session=session) == []

    # A caregiver hands the session back while the stove is still on: every
    # condition is armed again, so the hazard escalates once more.
    GuidedTaskStore(db_factory).add_event(
        session_id=session_id,
        at=clock.now,
        kind="takeover_ended",
        step_ord=0,
        actor="caregiver",
    )
    clock.now += timedelta(seconds=20)
    rearmed = {event["condition"] for event in await watch.evaluate(session=session)}
    assert "hazard_active" in rearmed
    assert "left_expected_room" in rearmed
    # The fall signal arrived before the release, so it is not raised again.
    assert "no_motion" not in rearmed


async def test_fall_signal_before_step_entry_is_ignored(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    stale = session.started_at - timedelta(minutes=5)
    watch = _watch(db_factory, _Clock(now=session.started_at), signals_service=_TimedSignals(stale))

    assert await watch.evaluate(session=session) == []


async def test_fall_signal_before_a_retry_still_fires(db_session, db_factory) -> None:
    """A retry bumps last_activity_at; anchoring on it would hide this fall."""
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    fall_at = session.started_at + timedelta(seconds=5)
    session.last_activity_at = session.started_at + timedelta(seconds=10)
    db_session.commit()
    clock = _Clock(now=session.started_at + timedelta(seconds=15))
    watch = _watch(db_factory, clock, signals_service=_TimedSignals(fall_at))

    events = await watch.evaluate(session=session)

    assert [event["condition"] for event in events] == ["no_motion"]


async def test_blocked_reports_count_only_since_the_step_was_armed(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    store = GuidedTaskStore(db_factory)
    entered = session.started_at + timedelta(seconds=60)
    store.add_event(
        session_id=session_id,
        at=session.started_at + timedelta(seconds=10),
        kind="step_blocked",
        step_ord=0,
        actor="resident",
    )
    store.add_event(
        session_id=session_id, at=entered, kind="step_entered", step_ord=0, actor="system"
    )
    store.add_event(
        session_id=session_id,
        at=entered + timedelta(seconds=5),
        kind="step_blocked",
        step_ord=0,
        actor="resident",
    )
    watch = _watch(db_factory, _Clock(now=entered + timedelta(seconds=10)))

    assert await watch.evaluate(session=session) == []


class _ReCameraAggregator:
    def __init__(self) -> None:
        self.sensors: list[str] = []

    async def query_media_by_sensor(self, *, sensor_ids_ordered, **kwargs):
        self.sensors = list(sensor_ids_ordered)
        return ["https://minio/recamera/recam-1/20261123_090000.jpg"]


class _ReCameraMinio(_Minio):
    def __init__(self) -> None:
        self.fetched: list[str] = []

    def extract_object_name(self, url: str) -> str:
        return url.removeprefix("https://minio/")

    async def async_get_object(self, object_name: str) -> bytes:
        self.fetched.append(object_name)
        return b"image"


async def test_hazard_uses_recamera_frames_without_cts(db_session, db_factory) -> None:
    """A reCamera-only kitchen (no CTS bucketizer) must still be checked for hazards."""
    session_id = _seed(db_session, safety_critical=True)
    db_session.query(RoutineStep).update({"camera_ids": ["recam-1"]})
    db_session.commit()
    session = db_session.get(GuidedSession, session_id)
    aggregator = _ReCameraAggregator()
    minio = _ReCameraMinio()
    watch = _watch(
        db_factory,
        _Clock(),
        event_aggregator=aggregator,
        camera_source_resolver=lambda _camera_id: "recamera",
        scene_analysis_client=_Scene([_Hazard()]),
        minio_client=minio,
    )

    events = await watch.evaluate(session=session)

    assert aggregator.sensors == ["recam-1"]
    assert minio.fetched == ["recamera/recam-1/20261123_090000.jpg"]
    hazard = next(event for event in events if event["condition"] == "hazard_active")
    assert hazard["detail"]["cameras"] == [{"id": "recam-1", "source": "recamera"}]
    assert hazard["detail"]["source"] == "recamera"


# ---------------------------------------------------------------------------
# Watch.tick: one escalation per tick, never on a summoning session
# ---------------------------------------------------------------------------


class _FixedSafetyWatch:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.calls = 0

    async def evaluate(self, *, session):
        self.calls += 1
        return [dict(event) for event in self.events]


async def test_tick_coalesces_conditions_into_one_escalation(db_session, db_factory) -> None:
    routine_id = _seed_service_routine(db_session)
    clock = _Clock()
    escalator = _RecordingEscalator()
    safety = _FixedSafetyWatch(
        [
            {"condition": "left_expected_room", "severity": "high", "detail": {}},
            {"condition": "hazard_active", "severity": "emergency", "detail": {}},
            {"condition": "confusion_distress", "severity": "high", "detail": {}},
        ]
    )
    service = GuidedTaskService(
        db_factory=db_factory,
        escalator=escalator,
        safety_watch=safety,
        settings=_settings(),
        time_fn=clock,
    )
    session = await service.start(routine_id, "resident-1")

    clock.now += timedelta(seconds=20)
    await service.tick(clock.now)

    assert escalator.calls == [(session.id, "hazard_active", True)]
    rows = (
        db_session.query(GuidedSessionEvent)
        .filter_by(session_id=session.id, kind="safety_event")
        .order_by(GuidedSessionEvent.id)
        .all()
    )
    assert sorted(row.detail["condition"] for row in rows) == [
        "confusion_distress",
        "hazard_active",
        "left_expected_room",
    ]
    assert {row.detail.get("coalesced_into") for row in rows} == {"hazard_active", None}


async def test_tick_skips_safety_for_summoning_session(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    db_session.get(GuidedSession, session_id).status = "summoning"
    db_session.commit()
    safety = _FixedSafetyWatch([{"condition": "left_expected_room", "severity": "high"}])
    escalator = _RecordingEscalator()
    clock = _Clock()
    service = GuidedTaskService(
        db_factory=db_factory,
        escalator=escalator,
        safety_watch=safety,
        settings=_settings(),
        time_fn=clock,
    )

    await service.tick(clock.now + timedelta(seconds=20))

    assert safety.calls == 0
    assert escalator.calls == []
