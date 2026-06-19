from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine
from backend.models.person import HouseholdMember
from backend.services.guided_task.metrics_service import GuidedMetricsService

_NOW = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


def _seed_routine(db_session) -> int:
    member = db_session.get(HouseholdMember, "resident-1")
    if not member:
        db_session.add(HouseholdMember(id="resident-1", name="Resident"))
        db_session.flush()

    routine = Routine(name="Routine", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    db_session.commit()
    return routine.id


def _session(
    db_session,
    routine_id: int,
    *,
    started_at: datetime,
    completed_at: datetime | None = None,
    status: str = "completed",
    outcome: str | None = "completed",
) -> GuidedSession:
    session = GuidedSession(
        routine_id=routine_id,
        person_id="resident-1",
        started_at=started_at,
        last_activity_at=completed_at or started_at,
        completed_at=completed_at,
        status=status,
        outcome=outcome,
        current_step_ord=0,
        attempts=0,
    )
    db_session.add(session)
    db_session.flush()
    return session


def _event(
    db_session,
    session: GuidedSession,
    *,
    kind: str,
    step_ord: int | None = 0,
    detail: dict | None = None,
    at: datetime | None = None,
) -> GuidedSessionEvent:
    event = GuidedSessionEvent(
        session_id=session.id,
        at=at or _NOW,
        kind=kind,
        step_ord=step_ord,
        actor="system",
        detail=detail or {},
    )
    db_session.add(event)
    db_session.flush()
    return event


def _svc(db_factory) -> GuidedMetricsService:
    return GuidedMetricsService(
        db_factory=db_factory,
        settings=Settings.from_dict({"app": {"timezone": "America/New_York"}}),
        time_fn=lambda: _NOW,
    )


def test_vision_agreement_reads_new_detail_shape(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    session = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=2),
        completed_at=_NOW - timedelta(hours=1),
        status="completed",
        outcome="completed",
    )

    # Seed events with the new shape: complete & confidence
    # 1. Complete=True, confidence=0.8 (Agreed=True, Uncertain=False)
    _event(
        db_session,
        session,
        kind="vision_confirm",
        detail={"complete": True, "confidence": 0.8, "profile": "confirm"},
        at=_NOW - timedelta(minutes=50),
    )
    # 2. Complete=False, confidence=0.4 (Agreed=False, Uncertain=True because < 0.7)
    _event(
        db_session,
        session,
        kind="vision_confirm",
        detail={"complete": False, "confidence": 0.4, "profile": "confirm"},
        at=_NOW - timedelta(minutes=40),
    )
    db_session.commit()

    result = _svc(db_factory).vision_agreement(person_id="resident-1", routine_id=routine_id)

    assert result.total == 2
    assert result.agreed == 1
    # 0.4 is less than 0.7, so it counts as uncertain
    assert result.uncertain == 1
    assert result.agreement_rate == 0.5


def test_watch_summary_counts_and_agreement(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    session = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=2),
        completed_at=_NOW - timedelta(hours=1),
        status="completed",
        outcome="completed",
    )

    # 1. Watch run 1: complete=True, conf=0.9
    _event(
        db_session,
        session,
        kind="watch",
        detail={
            "complete": True,
            "confidence": 0.9,
            "profile": "watch",
            "cost": {"model_calls": 1, "frames": 3, "latency_ms": 100.0},
        },
        at=_NOW - timedelta(minutes=50),
    )
    # 2. Confirm run 1 (after watch 1): complete=True
    _event(
        db_session,
        session,
        kind="vision_confirm",
        detail={"complete": True, "confidence": 0.9, "profile": "confirm"},
        at=_NOW - timedelta(minutes=45),
    )

    # 3. Watch run 2: complete=True, conf=0.8
    _event(
        db_session,
        session,
        kind="watch",
        detail={
            "complete": True,
            "confidence": 0.8,
            "profile": "watch",
            "cost": {"model_calls": 1, "frames": 3, "latency_ms": 150.0},
        },
        at=_NOW - timedelta(minutes=40),
    )
    # 4. Confirm run 2 (after watch 2): complete=False (disagreement)
    _event(
        db_session,
        session,
        kind="vision_confirm",
        detail={"complete": False, "confidence": 0.6, "profile": "confirm"},
        at=_NOW - timedelta(minutes=35),
    )

    # 5. Watch auto advance event
    _event(
        db_session,
        session,
        kind="step_completed",
        detail={"completion_reason": "watch_auto_advance", "streak": 3},
        at=_NOW - timedelta(minutes=30),
    )

    db_session.commit()

    result = _svc(db_factory).watch_summary(person_id="resident-1", routine_id=routine_id)

    assert result.total_runs == 2
    assert result.auto_advances == 1
    # Costs check
    assert result.average_model_calls == 1.0
    assert result.average_frames == 3.0
    assert result.average_latency_ms == 125.0
    # Agreement check:
    # - Run 1: watch (True) vs confirm (True) -> Agreed
    # - Run 2: watch (True) vs confirm (False) -> Disagreed
    # Total comparisons = 2, agreed = 1 -> agreement_rate = 0.5
    assert result.agreement_rate == 0.5


def test_gate_cost_summary_aggregates_cost(db_session, db_factory) -> None:
    routine_id = _seed_routine(db_session)
    session = _session(
        db_session,
        routine_id,
        started_at=_NOW - timedelta(hours=2),
        completed_at=_NOW - timedelta(hours=1),
        status="completed",
        outcome="completed",
    )

    # Seed watch costs
    _event(
        db_session,
        session,
        kind="watch",
        detail={"cost": {"model_calls": 1, "frames": 3, "latency_ms": 100.0}},
        at=_NOW - timedelta(minutes=50),
    )
    _event(
        db_session,
        session,
        kind="watch",
        detail={"cost": {"model_calls": 2, "frames": 6, "latency_ms": 200.0}},
        at=_NOW - timedelta(minutes=40),
    )

    # Seed confirm costs
    _event(
        db_session,
        session,
        kind="vision_confirm",
        detail={"cost": {"model_calls": 3, "frames": 9, "latency_ms": 500.0}},
        at=_NOW - timedelta(minutes=30),
    )

    db_session.commit()

    result = _svc(db_factory).gate_cost_summary(person_id="resident-1", routine_id=routine_id)

    # Watch total: calls = 3, frames = 9, latency = 300
    assert result.watch_cost.model_calls == 3
    assert result.watch_cost.frames == 9
    assert result.watch_cost.latency_ms == 300.0

    # Confirm total: calls = 3, frames = 9, latency = 500
    assert result.confirm_cost.model_calls == 3
    assert result.confirm_cost.frames == 9
    assert result.confirm_cost.latency_ms == 500.0

    # Total aggregate: calls = 6, frames = 18, latency = 800
    assert result.total_cost.model_calls == 6
    assert result.total_cost.frames == 18
    assert result.total_cost.latency_ms == 800.0
