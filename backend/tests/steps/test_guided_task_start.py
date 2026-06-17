"""Tests for GuidedTaskStartStep."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

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
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def request_start(self, routine_id: int, person_id: str, **kwargs):
        self.calls.append({"routine_id": routine_id, "person_id": person_id, **kwargs})
        return type("Session", (), {"id": 99, "status": "summoning"})()


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
    routine = _add_routine(db_session)
    db_session.add(
        GuidedSession(
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
    )
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
    assert guided_task.calls == []
