"""Tests for GuidedTaskStartStep."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import settings
from backend.core.exceptions import ConflictError
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.steps.base import ServiceContainer
from backend.steps.builtin.guided_task_start import GuidedTaskStartStep


@dataclass
class _Step:
    id: int
    step_type: str
    config_json: dict
    rule_id: int | None = None


@dataclass
class _Execution:
    id: int


class _GuidedTask:
    def __init__(self, *, conflict: bool = False, live_session_id: int | None = None) -> None:
        self.calls: list[dict] = []
        self._conflict = conflict
        self._live_session_id = live_session_id

    async def request_start(self, routine_id: int, person_id: str, **kwargs):
        self.calls.append({"routine_id": routine_id, "person_id": person_id, **kwargs})
        if self._conflict:
            raise ConflictError(f"Live guided session already exists for person '{person_id}'")
        return type("Session", (), {"id": 99, "status": "summoning"})()

    def get_live_session_for_person(self, person_id: str):
        if self._live_session_id is None:
            return None
        return type("Session", (), {"id": self._live_session_id})()


def _add_routine(db_session, person_id: str = "person-1") -> Routine:
    db_session.add(HouseholdMember(id=person_id, name="Ruth"))
    db_session.commit()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True)
    routine.steps.append(RoutineStep(ord=0, prompt_template="Boil water."))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)
    return routine


@pytest.mark.asyncio
async def test_missing_routine_id_returns_error(db_factory):
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=_GuidedTask())

    result = await handler.execute(
        _Step(id=1, step_type="guided_task_start", config_json={}),
        _Execution(id=10),
        {},
        None,
        services,
    )

    assert result.success is False
    assert result.data["error"] == "routine_id is required"


@pytest.mark.asyncio
async def test_missing_service_returns_error(db_factory):
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=None)

    result = await handler.execute(
        _Step(id=1, step_type="guided_task_start", config_json={"routine_id": 1}),
        _Execution(id=10),
        {},
        None,
        services,
    )

    assert result.success is False
    assert result.data["error"] == "guided task service not available"


@pytest.mark.asyncio
async def test_starts_session_and_parks(db_factory, db_session):
    routine = _add_routine(db_session)
    guided_task = _GuidedTask()
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=guided_task)

    result = await handler.execute(
        _Step(
            id=1,
            step_type="guided_task_start",
            config_json={"routine_id": routine.id, "summon_timeout_s": 120},
        ),
        _Execution(id=10),
        {},
        None,
        services,
    )

    assert result.success is True
    assert result.wait_until is not None
    assert result.data["guided_session_id"] == 99
    assert guided_task.calls == [
        {
            "routine_id": routine.id,
            "person_id": "person-1",
            "execution_id": 10,
            "require_presence": True,
            "summon_timeout_s": 120,
        }
    ]


@pytest.mark.asyncio
async def test_dedupe_skips_recent_completed_routine(db_factory, db_session):
    """Two completions inside the dedupe window must not raise MultipleResultsFound (G7)."""
    routine = _add_routine(db_session)
    older = GuidedSession(
        routine_id=routine.id,
        person_id="person-1",
        status="completed",
        current_step_ord=0,
        attempts=0,
        started_at=datetime.now(UTC) - timedelta(minutes=40),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=40),
        completed_at=datetime.now(UTC) - timedelta(minutes=30),
        outcome="completed",
    )
    newer = GuidedSession(
        routine_id=routine.id,
        person_id="person-1",
        status="completed",
        current_step_ord=0,
        attempts=0,
        started_at=datetime.now(UTC) - timedelta(minutes=20),
        last_activity_at=datetime.now(UTC) - timedelta(minutes=20),
        completed_at=datetime.now(UTC) - timedelta(minutes=10),
        outcome="completed",
    )
    db_session.add_all([older, newer])
    db_session.commit()
    guided_task = _GuidedTask()
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=guided_task)

    result = await handler.execute(
        _Step(
            id=1,
            step_type="guided_task_start",
            config_json={"routine_id": routine.id, "dedupe_hours": 1},
        ),
        _Execution(id=10),
        {},
        None,
        services,
    )

    assert result.success is True
    assert result.data["skipped"] is True
    assert result.data["reason"] == "dedupe"
    assert result.data["prior_session_id"] == newer.id
    assert guided_task.calls == []


@pytest.mark.asyncio
async def test_live_session_conflict_returns_structured_skip(db_factory, db_session):
    """A ConflictError from request_start must not fail the step (G6/G7 addendum)."""
    routine = _add_routine(db_session)
    guided_task = _GuidedTask(conflict=True, live_session_id=55)
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=guided_task)

    result = await handler.execute(
        _Step(id=1, step_type="guided_task_start", config_json={"routine_id": routine.id}),
        _Execution(id=10),
        {},
        None,
        services,
    )

    assert result.success is True
    assert result.data["skipped"] is True
    assert result.data["reason"] == "live_session"
    assert result.data["prior_session_id"] == 55


@pytest.mark.asyncio
async def test_park_budget_covers_all_steps(db_factory, db_session):
    routine = _add_routine(db_session)  # step 0, no overrides: global 300s * 3 attempts
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=1,
            prompt_template="Steep.",
            step_timeout_s_override=600,
            max_step_attempts_override=2,
        )
    )
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=2,
            prompt_template="Pour.",
            step_timeout_s_override=120,
            max_step_attempts_override=1,
        )
    )
    db_session.commit()
    guided_task = _GuidedTask()
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=guided_task)

    before = datetime.now(UTC)
    result = await handler.execute(
        _Step(
            id=1,
            step_type="guided_task_start",
            config_json={"routine_id": routine.id, "summon_timeout_s": 120},
        ),
        _Execution(id=10),
        {},
        None,
        services,
    )
    after = datetime.now(UTC)

    assert result.success is True
    global_step_timeout_s = settings.as_int("guided_task.step_timeout_s")
    global_max_attempts = settings.as_int("guided_task.max_step_attempts")
    resume_grace_s = settings.as_int("guided_task.resume_grace_s")
    routine_budget_s = (global_step_timeout_s * global_max_attempts) + (600 * 2) + (120 * 1)
    expected_park_s = 120 + routine_budget_s + resume_grace_s
    assert before + timedelta(seconds=expected_park_s - 1) <= result.wait_until
    assert result.wait_until <= after + timedelta(seconds=expected_park_s + 1)
    assert result.data["parked_until"] == result.wait_until.isoformat()


@pytest.mark.asyncio
async def test_park_budget_capped_by_setting(db_factory, db_session):
    routine = _add_routine(db_session)
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=1,
            prompt_template="Absurd step.",
            step_timeout_s_override=100_000,
            max_step_attempts_override=100,
        )
    )
    db_session.commit()
    guided_task = _GuidedTask()
    handler = GuidedTaskStartStep()
    services = ServiceContainer(db_factory=db_factory, guided_task=guided_task)

    before = datetime.now(UTC)
    result = await handler.execute(
        _Step(id=1, step_type="guided_task_start", config_json={"routine_id": routine.id}),
        _Execution(id=10),
        {},
        None,
        services,
    )
    after = datetime.now(UTC)

    max_pipeline_park_s = settings.as_int("guided_task.max_pipeline_park_s")
    assert result.success is True
    assert before + timedelta(seconds=max_pipeline_park_s - 1) <= result.wait_until
    assert result.wait_until <= after + timedelta(seconds=max_pipeline_park_s + 1)
