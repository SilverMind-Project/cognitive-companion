"""M12 wave-3 addendum: a room-scoped rule with a guided_task_start step
fires end-to-end.

C1/C2 broke exactly the context-filtered rules a caregiver would use to
start routines ("when she enters the kitchen in the morning, start the tea
routine"): the async ``room`` filter crashed rule matching (C1), and even
if it hadn't, the engine never had a wired ``PersonLocationService`` to
check against (C2). This test proves the whole chain works on the running
event loop: context filter evaluated through the engine -> rule matched ->
pipeline executed -> guided_task_start step runs -> guided session created.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.filters import FilterRegistry
from backend.models.guided_task import GuidedSession, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.models.pipeline import PipelineStep
from backend.models.rule import Rule, RuleContext
from backend.models.sensor import Sensor
from backend.services.person_location.types import CurrentLocation
from backend.services.pipeline_executor import PipelineExecutor
from backend.services.rules_engine import RulesEngine
from backend.steps.base import ServiceContainer as SC
from backend.steps.base import TriggerContext

FilterRegistry.discover()


class _StubPersonLocationService:
    def __init__(self, current: CurrentLocation) -> None:
        self._current = current

    async def where_is(self, person_id: str, at: datetime | None = None):
        return self._current

    async def presence_history(self, *args, **kwargs):
        return []

    async def current_dwell(self, *args, **kwargs):
        return None


class _FakeGuidedTaskService:
    """Records the request and creates a real GuidedSession row, matching
    what the production GuidedTaskService.request_start does."""

    def __init__(self, db_factory) -> None:
        self.db_factory = db_factory
        self.calls: list[dict] = []

    async def request_start(self, routine_id: int, person_id: str, **kwargs):
        self.calls.append({"routine_id": routine_id, "person_id": person_id, **kwargs})
        db = self.db_factory()
        try:
            now = datetime.now(UTC)
            session = GuidedSession(
                routine_id=routine_id,
                person_id=person_id,
                execution_id=kwargs.get("execution_id"),
                status="summoning",
                started_at=now,
                last_activity_at=now,
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return session
        finally:
            db.close()


@pytest.mark.asyncio
async def test_room_scoped_rule_with_guided_task_start_fires_end_to_end(db_session, db_factory):
    # -- Seed: a household member, a routine, and a room-triggered sensor --
    db_session.add(HouseholdMember(id="mom", name="Mom"))
    db_session.commit()

    routine = Routine(name="Morning tea", person_id="mom", is_enabled=True)
    routine.steps.append(RoutineStep(ord=0, prompt_template="Let's make some tea."))
    db_session.add(routine)
    db_session.commit()
    db_session.refresh(routine)

    sensor = Sensor(id="kitchen-cam", name="kitchen-cam", sensor_type="camera", enabled=True)
    db_session.add(sensor)
    db_session.commit()

    rule = Rule(
        name="Kitchen morning routine",
        enabled=True,
        trigger_types=["sensor_event"],
        cool_off_minutes=0,
        max_daily_triggers=0,
    )
    db_session.add(rule)
    db_session.flush()
    db_session.add(
        RuleContext(
            rule_id=rule.id,
            context_type="room",
            config_json={"room_id": "kitchen", "person_id": "mom"},
        )
    )
    db_session.add(
        PipelineStep(
            rule_id=rule.id,
            order=1,
            step_type="guided_task_start",
            label="guided_task_start_1",
            config_json={"routine_id": routine.id, "require_presence": False},
            enabled=True,
        )
    )
    db_session.commit()

    # -- Shared container: person_location wired (room match) + guided_task --
    person_location = _StubPersonLocationService(
        CurrentLocation(
            person_id="mom",
            room_id="kitchen",
            room_name="Kitchen",
            since=datetime.now(UTC) - timedelta(minutes=2),
            entry_source="observed",
            confidence=0.9,
            is_inferred=False,
            quality="high",
            last_observed_at=datetime.now(UTC),
        )
    )
    guided_task = _FakeGuidedTaskService(db_factory)
    services = SC(db_factory=db_factory, person_location=person_location, guided_task=guided_task)

    engine = RulesEngine(services, tz_name="UTC")

    # 1. Context filter evaluated through the engine, on the running loop.
    matched = await engine.get_matching_rules(sensor, db_session)
    assert [r.id for r in matched] == [rule.id]

    # 2. Pipeline executed: guided_task_start step runs, guided session created.
    executor = PipelineExecutor(services, rules_engine=engine)
    trigger = TriggerContext(trigger_type="sensor_event", sensor_id=sensor.id, room_name="Kitchen")
    execution = await executor.execute(rule, trigger, db_session)

    assert guided_task.calls, "guided_task_start step never called request_start"
    assert guided_task.calls[0]["routine_id"] == routine.id
    assert guided_task.calls[0]["person_id"] == "mom"

    step_outputs = execution.pipeline_data_json["steps"]["guided_task_start_1"]["outputs"]
    assert step_outputs["routine_id"] == routine.id
    assert isinstance(step_outputs["guided_session_id"], int)

    created = db_session.get(GuidedSession, step_outputs["guided_session_id"])
    assert created is not None
    assert created.routine_id == routine.id
    assert created.person_id == "mom"
