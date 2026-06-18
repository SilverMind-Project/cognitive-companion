from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.metrics_service import GuidedMetricsService

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings.from_dict({"app": {"timezone": "America/New_York"}})


def _seed_routine(db_session) -> int:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    for ord_ in range(3):
        db_session.add(RoutineStep(routine_id=routine.id, ord=ord_, prompt_template="Step"))
    db_session.commit()
    return routine.id


def _session(
    db_session,
    routine_id: int,
    *,
    started_at: datetime,
    completed_at: datetime | None,
    status: str,
    outcome: str | None,
) -> GuidedSession:
    session = GuidedSession(
        routine_id=routine_id,
        person_id="resident-1",
        status=status,
        current_step_ord=0,
        attempts=0,
        started_at=started_at,
        last_activity_at=completed_at or started_at,
        completed_at=completed_at,
        outcome=outcome,
    )
    db_session.add(session)
    db_session.flush()
    return session


def _event(
    db_session,
    session: GuidedSession,
    *,
    kind: str,
    step_ord: int | None = None,
    detail: dict | None = None,
) -> None:
    db_session.add(
        GuidedSessionEvent(
            session_id=session.id,
            at=session.started_at + timedelta(minutes=1),
            kind=kind,
            step_ord=step_ord,
            actor="system",
            detail=detail,
        )
    )


def _svc(db_factory) -> GuidedMetricsService:
    return GuidedMetricsService(db_factory=db_factory, settings=_settings(), time_fn=lambda: _NOW)


def test_completion_rate(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(days=1),
        completed_at=_NOW - timedelta(days=1, minutes=-10),
        status="completed",
        outcome="completed",
    )
    _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=3),
        completed_at=_NOW - timedelta(hours=2),
        status="abandoned",
        outcome="abandoned",
    )
    db_session.commit()

    result = _svc(db_factory).completion_summary(person_id="resident-1", routine_id=routine_id)

    assert result.started == 2
    assert result.completed == 1
    assert result.completion_rate == 0.5


def test_attempts_per_step_identifies_stall_step(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    first = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=5),
        completed_at=_NOW - timedelta(hours=4),
        status="completed",
        outcome="completed",
    )
    second = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=3),
        completed_at=_NOW - timedelta(hours=2),
        status="completed",
        outcome="completed",
    )
    _event(db_session, first, kind="retry", step_ord=1)
    _event(db_session, first, kind="retry", step_ord=1)
    _event(db_session, second, kind="retry", step_ord=1)
    db_session.commit()

    result = _svc(db_factory).attempts_per_step(person_id="resident-1", routine_id=routine_id)

    assert result.items[0].step_ord == 1
    assert result.items[0].average_attempts == pytest.approx(1.5)
    assert result.items[0].max_attempts == 2
    assert result.items[0].retry_events == 3


def test_time_to_complete_median(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    for minutes in (10, 20, 30):
        started = _NOW - timedelta(days=1, minutes=minutes)
        _session(
            db_session,
            routine_id,
            started_at=started,
            completed_at=started + timedelta(minutes=minutes),
            status="completed",
            outcome="completed",
        )
    db_session.commit()

    result = _svc(db_factory).time_to_complete(person_id="resident-1", routine_id=routine_id)

    assert result.items[0].median_seconds == pytest.approx(1200.0)
    assert result.items[0].average_seconds == pytest.approx(1200.0)


def test_abandonment_reasons(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    session = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=2),
        completed_at=_NOW - timedelta(hours=1),
        status="abandoned",
        outcome="abandoned",
    )
    _event(db_session, session, kind="session_abandoned", detail={"reason": "wandered_off"})
    db_session.commit()

    result = _svc(db_factory).abandonment(person_id="resident-1", routine_id=routine_id)

    assert result.abandoned == 1
    assert result.abandonment_rate == 1.0
    assert result.reasons[0].reason == "wandered_off"
    assert result.reasons[0].count == 1


def test_escalation_breakdown_emergency_vs_high(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    session = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=2),
        completed_at=_NOW - timedelta(hours=1),
        status="completed",
        outcome="escalated_resolved",
    )
    _event(db_session, session, kind="escalation", detail={"reason": "hazard", "emergency": True})
    _event(
        db_session,
        session,
        kind="escalation",
        detail={"reason": "attempts_exhausted", "emergency": False},
    )
    db_session.commit()

    result = _svc(db_factory).escalation_breakdown(person_id="resident-1", routine_id=routine_id)

    assert result.total == 2
    assert result.emergency_total == 1


def test_vision_agreement_rate(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    session = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=2),
        completed_at=_NOW - timedelta(hours=1),
        status="completed",
        outcome="completed",
    )
    _event(db_session, session, kind="vision_confirm", detail={"agreed": True})
    _event(db_session, session, kind="vision_confirm", detail={"agreed": False, "uncertain": True})
    db_session.commit()

    result = _svc(db_factory).vision_agreement(person_id="resident-1", routine_id=routine_id)

    assert result.total == 2
    assert result.agreed == 1
    assert result.uncertain == 1
    assert result.agreement_rate == 0.5


def test_time_of_day_buckets_in_app_timezone(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    started = datetime(2026, 6, 18, 3, 30, tzinfo=UTC)
    _session(
        db_session,
        routine_id,
        started_at=started,
        completed_at=started + timedelta(minutes=5),
        status="completed",
        outcome="completed",
    )
    db_session.commit()

    result = _svc(db_factory).time_of_day(person_id="resident-1", routine_id=routine_id)

    assert result.timezone == "America/New_York"
    assert result.buckets[23].completed == 1


def test_empty_window_returns_zeros_not_error(db_factory) -> None:
    result = _svc(db_factory).dashboard(person_id="resident-1")

    assert result.completion.started == 0
    assert result.abandonment.abandoned == 0
    assert result.vision_agreement.total == 0
