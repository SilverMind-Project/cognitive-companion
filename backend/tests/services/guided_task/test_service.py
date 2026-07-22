from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.core.config import Settings
from backend.core.exceptions import ConflictError
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.observability.metrics import location_metrics as guided_metrics
from backend.services.guided_task.service import GuidedTaskService


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _RecordingVoice:
    calls: list[tuple[int, str, bool]] = field(default_factory=list)

    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        self.calls.append((step.ord, rendered_prompt, is_retry))


@dataclass
class _RecordingEscalator:
    calls: list[tuple[int, str, bool]] = field(default_factory=list)

    async def escalate(self, *, session, reason: str, emergency: bool) -> None:
        self.calls.append((session.id, reason, emergency))


@dataclass
class _SafetyWatch:
    events: list[dict]
    calls: int = 0

    async def evaluate(self, *, session) -> list[dict]:
        self.calls += 1
        return self.events


class _FakeSchedulerBackend:
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


@dataclass
class _FakeScheduler:
    apscheduler: _FakeSchedulerBackend = field(default_factory=_FakeSchedulerBackend)


@dataclass
class _FakePipelineExecutor:
    resumed: list[int] = field(default_factory=list)

    def resume(self, execution_id: int, db) -> None:
        self.resumed.append(execution_id)


@dataclass
class _SceneIntel:
    """Fake ``SceneIntelService`` capturing drafts passed to ``persist_observation``."""

    drafts: list = field(default_factory=list)

    async def persist_observation(self, draft):
        from backend.services.scene_intel.types import SceneIntelRecord

        self.drafts.append(draft)
        return SceneIntelRecord(observation_id=len(self.drafts))


def _settings(max_step_attempts: int = 3, resume_grace_s: int = 600) -> Settings:
    return Settings.from_dict(
        {
            "app": {"timezone": "America/New_York"},
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": max_step_attempts,
                "resume_grace_s": resume_grace_s,
                "transcript_retention_days": 30,
            },
        }
    )


def _seed_routine(db_session, *, steps: int = 2, execution_person_id: str = "resident-1") -> int:
    db_session.add(HouseholdMember(id=execution_person_id, name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id=execution_person_id, is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    for ord_ in range(steps):
        db_session.add(
            RoutineStep(
                routine_id=routine.id,
                ord=ord_,
                prompt_template=f"Step {ord_} for {{{{ session.person_id }}}}",
                completion_gate={"kinds": ["response"]},
                is_safety_critical=False,
            )
        )
    db_session.commit()
    return routine.id


def _service(
    db_factory,
    clock: _Clock,
    *,
    scheduler=None,
    voice: _RecordingVoice | None = None,
    escalator: _RecordingEscalator | None = None,
    safety_watch: _SafetyWatch | None = None,
    pipeline_executor=None,
    scene_intel=None,
    memory_query=None,
    knowledge_ingestion=None,
    settings: Settings | None = None,
) -> GuidedTaskService:
    return GuidedTaskService(
        db_factory=db_factory,
        scheduler=scheduler,
        pipeline_executor=pipeline_executor,
        voice=voice,
        escalator=escalator,
        safety_watch=safety_watch,
        scene_intel=scene_intel,
        memory_query=memory_query,
        knowledge_ingestion=knowledge_ingestion,
        settings=settings or _settings(),
        time_fn=clock,
    )


@pytest.mark.asyncio
async def test_start_creates_active_session_and_speaks_step0(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    clock = _Clock()
    voice = _RecordingVoice()
    scheduler = _FakeScheduler()
    service = _service(db_factory, clock, scheduler=scheduler, voice=voice)

    session = await service.start(routine_id, "resident-1")

    assert session.status == "active"
    assert session.current_step_ord == 0
    assert voice.calls == [(0, "Step 0 for resident-1", False)]
    assert scheduler.apscheduler.jobs[0]["id"] == f"guided_session_timeout_{session.id}"


@pytest.mark.asyncio
async def test_start_rejects_when_live_session_exists(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    service = _service(db_factory, _Clock())
    await service.start(routine_id, "resident-1")

    with pytest.raises(ConflictError):
        await service.start(routine_id, "resident-1")


@pytest.mark.asyncio
async def test_handle_completion_advances_to_next_step(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    clock = _Clock()
    voice = _RecordingVoice()
    service = _service(db_factory, clock, voice=voice)
    session = await service.start(routine_id, "resident-1")

    result = await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert result["advanced"] is True
    assert result["done"] is False
    assert result["next_step"]["step_ord"] == 1
    assert result["next_step"]["prompt_text"] == "Step 1 for resident-1"
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.current_step_ord == 1
    assert voice.calls == [(0, "Step 0 for resident-1", False)]


@pytest.mark.asyncio
async def test_handle_completion_on_last_step_completes_and_resumes_pipeline(
    db_session, db_factory
):
    routine_id = _seed_routine(db_session, steps=1)
    clock = _Clock()
    executor = _FakePipelineExecutor()
    service = _service(db_factory, clock, pipeline_executor=executor)
    session = await service.start(routine_id, "resident-1", execution_id=42)

    result = await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert result["advanced"] is True
    assert result["done"] is True
    assert result["next_step"] is None
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "completed"
    assert stored.outcome == "completed"
    assert executor.resumed == [42]


@pytest.mark.asyncio
async def test_duplicate_completion_is_idempotent(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    service = _service(db_factory, _Clock())
    session = await service.start(routine_id, "resident-1")
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    result = await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert result["advanced"] is False
    assert result["reason"] == "stale_step_completion"
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.current_step_ord == 1


@pytest.mark.asyncio
async def test_on_step_timeout_retries_then_escalates_at_cap(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    clock = _Clock()
    voice = _RecordingVoice()
    escalator = _RecordingEscalator()
    service = _service(
        db_factory,
        clock,
        voice=voice,
        escalator=escalator,
        settings=_settings(max_step_attempts=2),
    )
    session = await service.start(routine_id, "resident-1")

    first = await service.on_step_timeout(session.id)
    second = await service.on_step_timeout(session.id)

    assert first.kind == "retry"
    assert second.kind == "escalate"
    assert voice.calls[-1] == (0, "Step 0 for resident-1", True)
    assert escalator.calls == [(session.id, "attempts_exhausted", False)]


@pytest.mark.asyncio
async def test_resume_after_grace_abandons(db_session, db_factory):
    """M25/G6 addendum: a clean resume-grace abandon resumes the owning
    pipeline immediately, the same as any other terminal transition, rather
    than waiting out the park-ceiling backstop meant for a wedged session."""
    routine_id = _seed_routine(db_session)
    clock = _Clock()
    executor = _FakePipelineExecutor()
    service = _service(
        db_factory, clock, settings=_settings(resume_grace_s=60), pipeline_executor=executor
    )
    session = await service.start(routine_id, "resident-1", execution_id=42)
    clock.advance(61)

    decision = await service.resume(session.id)

    assert decision.kind == "abandon"
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "abandoned"
    assert stored.outcome == "abandoned"
    assert executor.resumed == [42]


@pytest.mark.asyncio
async def test_terminal_transition_invokes_bridge_on_complete(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=1)
    service = _service(db_factory, _Clock())
    calls: list[str] = []

    async def fake_terminal(session):
        calls.append(session.status)

    service._memory_bridge.on_session_terminal = fake_terminal
    session = await service.start(routine_id, "resident-1")

    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert calls == ["completed"]


@pytest.mark.asyncio
async def test_terminal_transition_invokes_bridge_on_abandon(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    clock = _Clock()
    service = _service(db_factory, clock, settings=_settings(resume_grace_s=60))
    calls: list[str] = []

    async def fake_terminal(session):
        calls.append(session.status)

    service._memory_bridge.on_session_terminal = fake_terminal
    session = await service.start(routine_id, "resident-1", execution_id=42)
    clock.advance(61)

    decision = await service.resume(session.id)

    assert decision.kind == "abandon"
    assert calls == ["abandoned"]


@pytest.mark.asyncio
async def test_terminal_transition_bridge_not_invoked_for_non_terminal_event(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=2)
    service = _service(db_factory, _Clock())
    calls: list[str] = []

    async def fake_terminal(session):
        calls.append(session.status)

    service._memory_bridge.on_session_terminal = fake_terminal
    session = await service.start(routine_id, "resident-1")

    # Advances step 0 -> step 1, a non-terminal transition.
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert calls == []


@pytest.mark.asyncio
async def test_missing_scheduler_is_graceful(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    service = _service(db_factory, _Clock(), scheduler=None)

    session = await service.start(routine_id, "resident-1")

    assert session.status == "active"


@pytest.mark.asyncio
async def test_complete_writes_observation_without_transcript(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=1)
    clock = _Clock()
    scene_intel = _SceneIntel()
    service = _service(db_factory, clock, scene_intel=scene_intel)
    session = await service.start(routine_id, "resident-1")

    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert len(scene_intel.drafts) == 1
    draft = scene_intel.drafts[0]
    assert draft.source == "guided_companion"
    assert draft.kind == "guided_episode"
    assert "Make tea" in draft.description
    assert "transcript" not in draft.description.lower()


@pytest.mark.asyncio
async def test_guided_metrics_counters_increment_on_finalize(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=1)
    service = _service(db_factory, _Clock())
    session = await service.start(routine_id, "resident-1")
    before_sessions = guided_metrics.guided_sessions_total.labels(outcome="completed")._value.get()
    before_steps = guided_metrics.guided_steps_total.labels(result="completed")._value.get()

    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert guided_metrics.guided_sessions_total.labels(outcome="completed")._value.get() == (
        before_sessions + 1
    )
    assert guided_metrics.guided_steps_total.labels(result="completed")._value.get() == (
        before_steps + 1
    )


@pytest.mark.asyncio
async def test_missing_memory_service_graceful(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=1)
    service = _service(db_factory, _Clock(), scene_intel=None)
    session = await service.start(routine_id, "resident-1")

    result = await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    assert result["done"] is True


@pytest.mark.asyncio
async def test_retention_prune_uses_configured_window(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=1)
    old_started = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    recent_started = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    old = GuidedSession(
        routine_id=routine_id,
        person_id="resident-1",
        status="completed",
        current_step_ord=0,
        attempts=0,
        started_at=old_started,
        last_activity_at=old_started,
        completed_at=old_started + timedelta(minutes=5),
        outcome="completed",
    )
    recent = GuidedSession(
        routine_id=routine_id,
        person_id="resident-1",
        status="completed",
        current_step_ord=0,
        attempts=0,
        started_at=recent_started,
        last_activity_at=recent_started,
        completed_at=recent_started + timedelta(minutes=5),
        outcome="completed",
    )
    db_session.add_all([old, recent])
    db_session.flush()
    old_id = old.id
    recent_id = recent.id
    db_session.add(
        GuidedSessionEvent(
            session_id=old.id,
            at=old_started,
            kind="session_completed",
            step_ord=0,
            actor="system",
        )
    )
    db_session.commit()
    service = _service(db_factory, _Clock())

    result = await service.prune_retained_data()

    assert result["sessions"] == 1
    db_session.expire_all()
    assert db_session.get(GuidedSession, old_id) is None
    assert db_session.get(GuidedSession, recent_id) is not None


@pytest.mark.asyncio
async def test_retention_prune_is_idempotent(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=1)
    old_started = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    db_session.add(
        GuidedSession(
            routine_id=routine_id,
            person_id="resident-1",
            status="completed",
            current_step_ord=0,
            attempts=0,
            started_at=old_started,
            last_activity_at=old_started,
            completed_at=old_started + timedelta(minutes=5),
            outcome="completed",
        )
    )
    db_session.commit()
    service = _service(db_factory, _Clock())

    first = await service.prune_retained_data()
    second = await service.prune_retained_data()

    assert first["sessions"] == 1
    assert second["sessions"] == 0


@pytest.mark.asyncio
async def test_events_written_with_correct_actor(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    service = _service(db_factory, _Clock())
    session = await service.start(routine_id, "resident-1")

    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    rows = list(
        db_session.execute(
            select(GuidedSessionEvent)
            .where(GuidedSessionEvent.session_id == session.id)
            .order_by(GuidedSessionEvent.id)
        )
        .scalars()
        .all()
    )
    actors_by_kind = [(row.kind, row.actor) for row in rows]
    assert ("step_entered", "system") in actors_by_kind
    assert ("step_completed", "resident") in actors_by_kind


@pytest.mark.asyncio
async def test_mcp_tool_path_duplicate_completion_is_noop(db_session, db_factory):
    """The real MCP tool forwards step_ord, so a repeated agent call for the same
    step is ignored instead of skipping the next step (F2 regression guard)."""
    from backend.mcp.server import _svc, mark_guided_step_complete

    routine_id = _seed_routine(db_session, steps=3)
    service = _service(db_factory, _Clock())
    session = await service.start(routine_id, "resident-1")

    original = _svc.guided_task_service
    _svc.guided_task_service = service
    try:
        first = await mark_guided_step_complete(session.id, 0)
        second = await mark_guided_step_complete(session.id, 0)
    finally:
        _svc.guided_task_service = original

    assert first["advanced"] is True
    assert second["advanced"] is False
    assert second["reason"] == "stale_step_completion"
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.current_step_ord == 1


@pytest.mark.asyncio
async def test_tick_evaluates_all_active_sessions_and_escalates(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    clock = _Clock()
    escalator = _RecordingEscalator()
    safety_watch = _SafetyWatch(
        events=[{"condition": "no_motion", "severity": "emergency", "detail": {}}]
    )
    service = _service(
        db_factory,
        clock,
        escalator=escalator,
        safety_watch=safety_watch,
    )
    session = await service.start(routine_id, "resident-1")

    await service.tick(clock.now)

    assert safety_watch.calls == 1
    assert escalator.calls == [(session.id, "no_motion", True)]
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "escalated"


@dataclass
class _MemoryQuery:
    hits: list = field(default_factory=list)

    async def search(self, **kwargs):
        return self.hits


def _seed_routine_with_prompt(db_session, prompt_template: str) -> Routine:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    routine.steps.append(RoutineStep(ord=0, prompt_template=prompt_template))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


@pytest.mark.asyncio
async def test_session_prompt_includes_last_episode_sentence(db_session, db_factory):
    from backend.integrations.semantic_memory_client import ObservationSearchHit

    routine = _seed_routine_with_prompt(db_session, "Ready? {{ memory_context }}")
    hit = ObservationSearchHit(
        id=1,
        room_id="",
        observed_at=datetime.now(UTC),
        description=(
            "Guided routine 'Make tea' ended with outcome 'completed'. "
            "Duration 840 seconds. Started near local time 09:00. "
            "Completed steps: [0]. Skipped steps: none. Stalled steps: none. "
            "Total retries: 0. Escalations: 0."
        ),
        object_list=["Make tea"],
        hazard_flags=[],
        kind="guided_episode",
        person_id="resident-1",
    )
    service = _service(db_factory, _Clock(), memory_query=_MemoryQuery(hits=[hit]))

    session = await service.start(routine.id, "resident-1")
    step = await service.get_active_step(session.id)

    assert "Last time this routine: completed in 14 minutes" in step["prompt_text"]


@pytest.mark.asyncio
async def test_session_prompt_without_history_unchanged(db_session, db_factory):
    routine = _seed_routine_with_prompt(db_session, "Ready? {{ memory_context }}")
    service = _service(db_factory, _Clock(), memory_query=_MemoryQuery(hits=[]))

    session = await service.start(routine.id, "resident-1")
    step = await service.get_active_step(session.id)

    assert step["prompt_text"] == "Ready? "


@dataclass
class _KnowledgeIngestion:
    docs: list = field(default_factory=list)

    def list_documents_by_tags(self, tags, *, limit=50):
        return self.docs


@pytest.mark.asyncio
async def test_session_prompt_includes_top_3_preferences_shortest_first(db_session, db_factory):
    routine = _seed_routine_with_prompt(db_session, "{{ preferences }}")
    docs = [
        _fake_doc("Likes the kitchen radio on low during tea"),
        _fake_doc("Two sugars"),
        _fake_doc("Prefers her tea lukewarm, not hot"),
        _fake_doc("No milk"),
    ]
    knowledge_ingestion = _KnowledgeIngestion(docs=docs)
    service = _service(db_factory, _Clock(), knowledge_ingestion=knowledge_ingestion)

    session = await service.start(routine.id, "resident-1")
    step = await service.get_active_step(session.id)

    assert step["prompt_text"] == '["No milk", "Two sugars", "Prefers her tea lukewarm, not hot"]'


def _fake_doc(source_text: str):
    from types import SimpleNamespace

    return SimpleNamespace(source_text=source_text)


@pytest.mark.asyncio
async def test_end_to_end_tea_run_ledger_episode_events_and_readback(db_session, db_factory):
    """Completion-criteria proof (DL-M05): a completed tea run produces one
    ledger row, one episodic observation, timeline trace events, and the
    *next* session's prompt carries the one-sentence read-back.

    Run against a real Postgres testcontainer end to end within the service
    layer; substitutes for exercising the live ``cc-backend`` deployment,
    which was not rebuilt/redeployed with this milestone's code (the same
    operator-action boundary DL-M01 documented for the semantic-memory flip).
    """
    from backend.integrations.semantic_memory_client import ObservationSearchHit
    from backend.models.person import ActivitySession
    from backend.services.activity_session import ActivitySessionService

    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(
        name="Make tea", person_id="resident-1", is_enabled=True, activity_type="meal_prep"
    )
    routine.steps.append(RoutineStep(ord=0, prompt_template="Boil water. {{ memory_context }}"))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)

    activity_service = ActivitySessionService(db_factory)
    scene_intel = _SceneIntel()
    clock = _Clock()
    # _service() doesn't take activity_service; build GuidedTaskService directly.
    service = GuidedTaskService(
        db_factory=db_factory,
        activity_service=activity_service,
        scene_intel=scene_intel,
        settings=_settings(),
        time_fn=clock,
    )

    session = await service.start(routine.id, "resident-1")
    await service.handle_completion(session.id, {"confirmed": True, "step_ord": 0})

    # 1. One ledger row, closed.
    ledger_rows = db_session.execute(
        select(ActivitySession).where(ActivitySession.person_id == "resident-1")
    ).scalars().all()
    assert len(ledger_rows) == 1
    assert ledger_rows[0].status == "closed"
    assert ledger_rows[0].activity_type == "meal_prep"

    # 2. One episodic observation, kind="guided_episode".
    assert len(scene_intel.drafts) == 1
    draft = scene_intel.drafts[0]
    assert draft.kind == "guided_episode"
    assert draft.person_id == "resident-1"

    # 3. Timeline trace events.
    detail = await service.get_detail(session.id)
    event_kinds = {e.kind for e in detail.recent_events}
    assert "ledger_recorded" in event_kinds
    assert "episode_recorded" in event_kinds

    # 4. The next session's prompt carries the one-sentence read-back,
    # fed from the episode this run just wrote.
    hit = ObservationSearchHit(
        id=1,
        room_id="",
        observed_at=datetime.now(UTC),
        description=draft.description,
        object_list=draft.object_list,
        hazard_flags=[],
        kind="guided_episode",
        person_id="resident-1",
    )
    service2 = GuidedTaskService(
        db_factory=db_factory,
        activity_service=ActivitySessionService(db_factory),
        scene_intel=_SceneIntel(),
        memory_query=_MemoryQuery(hits=[hit]),
        settings=_settings(),
        time_fn=_Clock(),
    )
    next_session = await service2.start(routine.id, "resident-1")
    step = await service2.get_active_step(next_session.id)
    assert "Last time this routine:" in step["prompt_text"]
