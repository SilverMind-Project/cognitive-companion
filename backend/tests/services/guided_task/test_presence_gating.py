"""Presence-gating tests for GuidedTaskService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.core.exceptions import ConflictError
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.companion_surface import SurfaceView
from backend.services.guided_task.service import GuidedTaskService


@dataclass(frozen=True)
class _Location:
    room_id: int
    room_name: str = "Kitchen"


class _PersonLocation:
    def __init__(self, location: _Location | None) -> None:
        self.location = location

    async def where_is(self, person_id: str) -> _Location | None:
        return self.location


class _Surfaces:
    def __init__(self, surfaces: list[SurfaceView]) -> None:
        self.surfaces = surfaces
        self.cross_checks: list[tuple[str, str]] = []

    def surfaces_in_room(self, room_id: int) -> list[SurfaceView]:
        return [s for s in self.surfaces if s.room_id == room_id and s.is_enabled]

    async def cross_check_room(self, surface_id: str, person_id: str) -> None:
        self.cross_checks.append((surface_id, person_id))


class _Ws:
    def __init__(self, live: bool, conversation_session_id: int | None = None) -> None:
        self.has_connections = live
        self.current_conversation_session_id = conversation_session_id


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        return {"pwa_popup_text": True}


class _Scheduler:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def add_job(self, finalize, trigger, run_date, id, args, replace_existing):
        self.jobs.append(
            {
                "finalize": finalize,
                "trigger": trigger,
                "run_date": run_date,
                "id": id,
                "args": args,
                "replace_existing": replace_existing,
            }
        )


class _Pipeline:
    def __init__(self) -> None:
        self.resumed: list[int] = []

    def resume(self, execution_id: int, db) -> None:
        self.resumed.append(execution_id)


def _settings() -> Settings:
    return Settings.from_dict(
        {
            "guided_task": {
                "max_step_attempts": 3,
                "step_timeout_s": 300,
                "resume_grace_s": 600,
                "summon_channels": ["pwa_popup_text"],
                "summon_messages": {
                    "en": "Please come to the companion screen when you are ready for your routine."
                },
            }
        }
    )


def _surface(room_id: int = 1) -> SurfaceView:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    return SurfaceView(
        id="kitchen-tablet",
        name="Kitchen Tablet",
        surface_type="movable",
        room_id=room_id,
        room_source="caregiver",
        kind="tablet",
        is_enabled=True,
        last_seen_at=None,
        room_mismatch=False,
        created_at=now,
        updated_at=now,
    )


def _add_routine(db_session, person_id: str = "person-1") -> Routine:
    db_session.add(HouseholdMember(id=person_id, name="Ruth"))
    db_session.commit()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True)
    routine.steps.append(RoutineStep(ord=0, prompt_template="Boil water."))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


def _service(
    db_factory,
    *,
    now: datetime,
    location: _Location | None,
    surfaces: list[SurfaceView] | None,
    live: bool,
    dispatcher: _Dispatcher | None = None,
    scheduler: _Scheduler | None = None,
    pipeline: _Pipeline | None = None,
) -> GuidedTaskService:
    return GuidedTaskService(
        db_factory=db_factory,
        scheduler=scheduler,
        pipeline_executor=pipeline,
        person_location_service=_PersonLocation(location),
        companion_surface_service=_Surfaces(surfaces or []),
        ws_manager=_Ws(live),
        notification_dispatcher=dispatcher,
        settings=_settings(),
        time_fn=lambda: now,
    )


@pytest.mark.asyncio
async def test_present_with_live_session_begins_immediately(db_factory, db_session):
    routine = _add_routine(db_session)
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        location=_Location(room_id=1),
        surfaces=[_surface(1)],
        live=True,
        scheduler=_Scheduler(),
    )

    session = await svc.request_start(routine.id, "person-1")

    assert session.status == "active"
    assert session.surface_id == "kitchen-tablet"


@pytest.mark.asyncio
async def test_present_without_live_session_summons_and_parks(db_factory, db_session):
    routine = _add_routine(db_session)
    dispatcher = _Dispatcher()
    scheduler = _Scheduler()
    surfaces = _Surfaces([_surface(1)])
    svc = GuidedTaskService(
        db_factory=db_factory,
        scheduler=scheduler,
        person_location_service=_PersonLocation(_Location(room_id=1)),
        companion_surface_service=surfaces,
        ws_manager=_Ws(False),
        notification_dispatcher=dispatcher,
        settings=_settings(),
        time_fn=lambda: datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
    )

    session = await svc.request_start(routine.id, "person-1", summon_timeout_s=120)

    assert session.status == "summoning"
    assert dispatcher.calls
    assert scheduler.jobs[0]["id"] == f"guided_summon_recheck_{session.id}"
    assert surfaces.cross_checks == [("kitchen-tablet", "person-1")]


@pytest.mark.asyncio
async def test_no_location_data_summons_broadly(db_factory, db_session):
    routine = _add_routine(db_session)
    dispatcher = _Dispatcher()
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        location=None,
        surfaces=[],
        live=False,
        dispatcher=dispatcher,
        scheduler=_Scheduler(),
    )

    session = await svc.request_start(routine.id, "person-1")

    event = (
        db_session.query(GuidedSessionEvent)
        .filter(GuidedSessionEvent.session_id == session.id)
        .filter(GuidedSessionEvent.kind == "summon_announced")
        .one()
    )
    assert event.detail["broad"] is True


@pytest.mark.asyncio
async def test_require_presence_false_begins_regardless(db_factory, db_session):
    routine = _add_routine(db_session)
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        location=None,
        surfaces=[],
        live=False,
        scheduler=_Scheduler(),
    )

    session = await svc.request_start(routine.id, "person-1", require_presence=False)

    assert session.status == "active"


@pytest.mark.asyncio
async def test_summon_recheck_begins_when_present_and_live(db_factory, db_session):
    routine = _add_routine(db_session)
    session = GuidedSession(
        routine_id=routine.id,
        person_id="person-1",
        status="summoning",
        current_step_ord=0,
        attempts=0,
        started_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        last_activity_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 1, tzinfo=UTC),
        location=_Location(room_id=1),
        surfaces=[_surface(1)],
        live=True,
        scheduler=_Scheduler(),
    )

    await svc._summon_recheck(session.id, 300)

    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).status == "active"


@pytest.mark.asyncio
async def test_summon_timeout_abandons_and_resumes_pipeline(db_factory, db_session):
    routine = _add_routine(db_session)
    session = GuidedSession(
        routine_id=routine.id,
        person_id="person-1",
        execution_id=42,
        status="summoning",
        current_step_ord=0,
        attempts=0,
        started_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        last_activity_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    pipeline = _Pipeline()
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 6, tzinfo=UTC),
        location=None,
        surfaces=[],
        live=False,
        pipeline=pipeline,
    )

    await svc._summon_recheck(session.id, 300)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "abandoned"
    assert stored.outcome == "summon_timeout"
    assert pipeline.resumed == [42]


@pytest.mark.asyncio
async def test_rejects_when_live_session_exists_for_person(db_factory, db_session):
    routine = _add_routine(db_session)
    db_session.add(
        GuidedSession(
            routine_id=routine.id,
            person_id="person-1",
            status="active",
            current_step_ord=0,
            attempts=0,
            started_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
            last_activity_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        )
    )
    db_session.commit()
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 1, tzinfo=UTC),
        location=None,
        surfaces=[],
        live=False,
    )

    with pytest.raises(ConflictError):
        await svc.request_start(routine.id, "person-1")


@pytest.mark.asyncio
async def test_on_session_opened_begins_summoning_session(db_factory, db_session):
    routine = _add_routine(db_session)
    session = GuidedSession(
        routine_id=routine.id,
        person_id="person-1",
        surface_id="kitchen-tablet",
        status="summoning",
        current_step_ord=0,
        attempts=0,
        started_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        last_activity_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    svc = _service(
        db_factory,
        now=datetime(2026, 6, 17, 12, 1, tzinfo=UTC),
        location=_Location(room_id=1),
        surfaces=[_surface(1)],
        live=True,
        scheduler=_Scheduler(),
    )

    await svc.on_session_opened()

    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).status == "active"


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.asyncio
async def test_on_session_opened_uses_original_summon_budget(db_factory, db_session):
    """G9: the recheck must use the session's real summon budget, not step_timeout_s."""
    routine = _add_routine(db_session)
    clock = _MutableClock(datetime(2026, 6, 17, 12, 0, tzinfo=UTC))
    svc = GuidedTaskService(
        db_factory=db_factory,
        scheduler=_Scheduler(),
        person_location_service=_PersonLocation(None),
        companion_surface_service=_Surfaces([]),
        ws_manager=_Ws(False),
        notification_dispatcher=_Dispatcher(),
        settings=_settings(),
        time_fn=clock,
    )

    session = await svc.request_start(routine.id, "person-1", summon_timeout_s=45)
    assert session.status == "summoning"

    # Past the session's real 45s summon budget, well below the global
    # step_timeout_s=300 the old (wrong) budget would have used.
    clock.advance(50)

    await svc.on_session_opened(conversation_session_id=None)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "abandoned"
    assert stored.outcome == "summon_timeout"
