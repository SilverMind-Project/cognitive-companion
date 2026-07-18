from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
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

    assert {
        "condition": "abandoned",
        "severity": "high",
        "detail": {"reason": "left_expected_room"},
    } in events


async def test_idle_beyond_timeout_emits_high(db_session, db_factory) -> None:
    session_id = _seed(db_session)
    session = db_session.get(GuidedSession, session_id)
    clock = _Clock(now=session.last_activity_at + timedelta(seconds=301))
    watch = _watch(db_factory, clock, settings=_settings(step_timeout_s=300))

    events = await watch.evaluate(session=session)

    assert any(
        event["condition"] == "abandoned" and event["detail"]["reason"] == "idle_timeout"
        for event in events
    )


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
