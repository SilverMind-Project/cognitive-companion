"""Tests for entry-time skip_condition dispatch (M25, G4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.service import GuidedTaskService


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)

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
class _Zone:
    id: int


class _ZoneService:
    """Reports the resident as always present in ``matching_zone_id``."""

    def __init__(self, matching_zone_id: int | None) -> None:
        self._matching_zone_id = matching_zone_id

    async def current_zone(self, person_id: str) -> _Zone | None:
        if self._matching_zone_id is None:
            return None
        return _Zone(id=self._matching_zone_id)


def _settings() -> Settings:
    return Settings.from_dict(
        {
            "app": {"timezone": "America/New_York"},
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": 3,
                "resume_grace_s": 600,
                "transcript_retention_days": 30,
            },
        }
    )


def _seed_routine(db_session, *, steps: list[dict]) -> int:
    person_id = "resident-1"
    db_session.add(HouseholdMember(id=person_id, name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    for ord_, step_kwargs in enumerate(steps):
        db_session.add(
            RoutineStep(
                routine_id=routine.id,
                ord=ord_,
                prompt_template=f"Step {ord_} for {{{{ session.person_id }}}}",
                completion_gate={"kinds": ["response"]},
                is_safety_critical=False,
                **step_kwargs,
            )
        )
    db_session.commit()
    return routine.id


def _service(
    db_factory,
    clock: _Clock,
    *,
    voice: _RecordingVoice | None = None,
    zone_service: _ZoneService | None = None,
) -> GuidedTaskService:
    return GuidedTaskService(
        db_factory=db_factory,
        voice=voice,
        zone_service=zone_service,
        settings=_settings(),
        time_fn=clock,
    )


@pytest.mark.asyncio
async def test_already_done_with_skip_condition_skips(db_session, db_factory):
    routine_id = _seed_routine(
        db_session,
        steps=[
            {"skip_condition": {"kind": "response_says_done"}},
            {},
        ],
    )
    clock = _Clock()
    voice = _RecordingVoice()
    service = _service(db_factory, clock, voice=voice)
    session = await service.start(routine_id, "resident-1")

    result = await service.handle_completion(
        session.id, {"confirmed": True, "step_ord": 0, "already_done": True}
    )

    assert result["advanced"] is True
    assert result["next_step"]["step_ord"] == 1
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.current_step_ord == 1
    assert stored.attempts == 0
    skip_event = (
        db_session.query(GuidedSessionEvent)
        .filter(
            GuidedSessionEvent.session_id == session.id,
            GuidedSessionEvent.kind == "step_skipped",
        )
        .one()
    )
    assert skip_event.step_ord == 0
    # Resident/agent-confirmed advances stay silent (the agent's own turn
    # owns the announcement); only the initial entry speak is expected.
    assert voice.calls == [(0, "Step 0 for resident-1", False)]


@pytest.mark.asyncio
async def test_already_done_without_skip_condition_completes_normally(db_session, db_factory):
    routine_id = _seed_routine(db_session, steps=[{}, {}])
    clock = _Clock()
    voice = _RecordingVoice()
    service = _service(db_factory, clock, voice=voice)
    session = await service.start(routine_id, "resident-1")

    result = await service.handle_completion(
        session.id, {"confirmed": True, "step_ord": 0, "already_done": True}
    )

    assert result["advanced"] is True
    assert result["next_step"]["step_ord"] == 1
    db_session.expire_all()
    assert (
        db_session.query(GuidedSessionEvent)
        .filter(
            GuidedSessionEvent.session_id == session.id,
            GuidedSessionEvent.kind == "step_completed",
        )
        .count()
        == 1
    )
    assert (
        db_session.query(GuidedSessionEvent)
        .filter(
            GuidedSessionEvent.session_id == session.id,
            GuidedSessionEvent.kind == "skip_condition_met",
        )
        .count()
        == 0
    )


@pytest.mark.asyncio
async def test_zone_presence_skip_on_entry(db_session, db_factory):
    """The entered step (0) is immediately skipped; only step 1 is spoken."""
    routine_id = _seed_routine(
        db_session,
        steps=[
            {"skip_condition": {"kind": "zone_presence", "zone_id": 7}},
            {},
        ],
    )
    clock = _Clock()
    voice = _RecordingVoice()
    zone_service = _ZoneService(matching_zone_id=7)
    service = _service(db_factory, clock, voice=voice, zone_service=zone_service)

    session = await service.start(routine_id, "resident-1")

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "active"
    assert stored.current_step_ord == 1
    skip_event = (
        db_session.query(GuidedSessionEvent)
        .filter(
            GuidedSessionEvent.session_id == session.id,
            GuidedSessionEvent.kind == "step_skipped",
        )
        .one()
    )
    assert skip_event.step_ord == 0
    # Exactly one speak, for the post-skip step; step 0 is never spoken.
    assert voice.calls == [(1, "Step 1 for resident-1", False)]


@pytest.mark.asyncio
async def test_consecutive_skips_bounded(db_session, db_factory):
    routine_id = _seed_routine(
        db_session,
        steps=[
            {"skip_condition": {"kind": "zone_presence", "zone_id": 7}},
            {"skip_condition": {"kind": "zone_presence", "zone_id": 7}},
            {"skip_condition": {"kind": "zone_presence", "zone_id": 7}},
        ],
    )
    clock = _Clock()
    voice = _RecordingVoice()
    zone_service = _ZoneService(matching_zone_id=7)
    service = _service(db_factory, clock, voice=voice, zone_service=zone_service)

    session = await service.start(routine_id, "resident-1")

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "completed"
    assert stored.outcome == "completed"
    assert voice.calls == []
    skip_events = (
        db_session.query(GuidedSessionEvent)
        .filter(
            GuidedSessionEvent.session_id == session.id,
            GuidedSessionEvent.kind == "step_skipped",
        )
        .all()
    )
    assert sorted(e.step_ord for e in skip_events) == [0, 1]
