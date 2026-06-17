from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.escalation.minimal import NotifyOnlyEscalator
from backend.services.guided_task.service import GuidedTaskService


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@dataclass
class _Voice:
    calls: list[tuple[int, str, bool]] = field(default_factory=list)

    async def speak_step(self, *, session, step, rendered_prompt: str, is_retry: bool) -> None:
        self.calls.append((step.ord, rendered_prompt, is_retry))


@dataclass
class _Pipeline:
    resumed: list[int] = field(default_factory=list)

    def resume(self, execution_id: int, db) -> None:
        self.resumed.append(execution_id)


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        return dict.fromkeys(kwargs["rule_config"]["channels"], True)


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


def _settings(max_step_attempts: int = 3) -> Settings:
    return Settings.from_dict(
        {
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": max_step_attempts,
                "resume_grace_s": 600,
                "escalation_channels": ["telegram", "pwa_popup_text"],
            }
        }
    )


def _seed_tea_routine(db_session, *, person_id: str = "resident-1") -> int:
    db_session.add(HouseholdMember(id=person_id, name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    prompts = [
        "Fill the kettle.",
        "Turn on the kettle.",
        "Put a tea bag in the cup.",
        "Pour the hot water.",
    ]
    for ord_, prompt in enumerate(prompts):
        db_session.add(
            RoutineStep(
                routine_id=routine.id,
                ord=ord_,
                prompt_template=prompt,
                completion_gate={"kinds": ["response"]},
            )
        )
    db_session.commit()
    return routine.id


def _service(
    db_factory,
    clock: _Clock,
    *,
    voice: _Voice,
    dispatcher: _Dispatcher,
    pipeline: _Pipeline | None = None,
    max_step_attempts: int = 3,
) -> GuidedTaskService:
    return GuidedTaskService(
        db_factory=db_factory,
        scheduler=_Scheduler(),
        pipeline_executor=pipeline,
        voice=voice,
        escalator=NotifyOnlyEscalator(
            dispatcher,
            db_factory=db_factory,
            settings=_settings(max_step_attempts=max_step_attempts),
        ),
        settings=_settings(max_step_attempts=max_step_attempts),
        time_fn=clock,
    )


@pytest.mark.asyncio
async def test_tea_routine_happy_path_advances_and_resumes_pipeline(
    db_session, db_factory
) -> None:
    routine_id = _seed_tea_routine(db_session)
    clock = _Clock()
    voice = _Voice()
    dispatcher = _Dispatcher()
    pipeline = _Pipeline()
    service = _service(db_factory, clock, voice=voice, dispatcher=dispatcher, pipeline=pipeline)

    session = await service.start(routine_id, "resident-1", execution_id=99)
    prompts: list[str] = [voice.calls[0][1]]
    for _ in range(4):
        result = await service.handle_completion(
            session.id,
            {"confirmed": True, "source": "agent"},
        )
        if result.get("next_step"):
            prompts.append(result["next_step"]["prompt_text"])

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    events = (
        db_session.query(GuidedSessionEvent)
        .filter(GuidedSessionEvent.session_id == session.id)
        .order_by(GuidedSessionEvent.id)
        .all()
    )
    assert stored.status == "completed"
    assert stored.outcome == "completed"
    assert prompts == [
        "Fill the kettle.",
        "Turn on the kettle.",
        "Put a tea bag in the cup.",
        "Pour the hot water.",
    ]
    assert pipeline.resumed == [99]
    assert [event.kind for event in events].count("step_completed") == 4


@pytest.mark.asyncio
async def test_tea_routine_help_request_notifies_caregiver(db_session, db_factory) -> None:
    routine_id = _seed_tea_routine(db_session)
    clock = _Clock()
    voice = _Voice()
    dispatcher = _Dispatcher()
    service = _service(db_factory, clock, voice=voice, dispatcher=dispatcher)
    session = await service.start(routine_id, "resident-1")

    await service.handle_completion(session.id, {"confirmed": True, "source": "agent"})
    result = await service.request_help(session.id, "resident_requested")

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert result == {"acknowledged": True}
    assert stored.status == "escalated"
    assert dispatcher.calls[0]["rule_config"]["channels"] == ["telegram", "pwa_popup_text"]


@pytest.mark.asyncio
async def test_tea_routine_timeout_retries_then_escalates(db_session, db_factory) -> None:
    routine_id = _seed_tea_routine(db_session)
    clock = _Clock()
    voice = _Voice()
    dispatcher = _Dispatcher()
    service = _service(
        db_factory,
        clock,
        voice=voice,
        dispatcher=dispatcher,
        max_step_attempts=2,
    )
    session = await service.start(routine_id, "resident-1")

    first = await service.on_step_timeout(session.id)
    second = await service.on_step_timeout(session.id)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert first.kind == "retry"
    assert second.kind == "escalate"
    assert voice.calls[-1] == (0, "Fill the kettle.", True)
    assert stored.status == "escalated"
    assert dispatcher.calls
