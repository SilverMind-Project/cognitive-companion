from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.escalation.full import FullEscalator
from backend.services.guided_task.service import GuidedTaskService


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        return dict.fromkeys(kwargs["rule_config"]["channels"], True)


@dataclass
class _WsManager:
    broadcasts: list[dict] = field(default_factory=list)

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)


@dataclass
class _PipelineExecutor:
    resumed: list[int] = field(default_factory=list)

    def resume(self, execution_id: int, db) -> None:
        self.resumed.append(execution_id)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


def _settings() -> Settings:
    return Settings.from_dict(
        {
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": 3,
                "resume_grace_s": 600,
                "escalation_grace_s": 1800,
                "escalation_channels": ["telegram", "pwa_popup_text"],
            }
        }
    )


def _seed(
    db_session,
    *,
    channels: list[str] | None = None,
    execution_id: int | None = None,
) -> GuidedSession:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(
        name="Make tea",
        person_id="resident-1",
        is_enabled=True,
        escalation_channels_override=channels,
    )
    db_session.add(routine)
    db_session.flush()
    db_session.add(RoutineStep(routine_id=routine.id, ord=0, prompt_template="Pour water."))
    session = GuidedSession(
        routine_id=routine.id,
        person_id="resident-1",
        execution_id=execution_id,
        status="active",
        current_step_ord=0,
        attempts=0,
        started_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        last_activity_at=datetime(2026, 6, 17, 12, 5, tzinfo=UTC),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_escalate_notifies_with_takeover_link(db_session, db_factory) -> None:
    session = _seed(db_session)
    dispatcher = _Dispatcher()
    escalator = FullEscalator(dispatcher, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="attempts_exhausted", emergency=False)

    assert dispatcher.calls[0]["alert_level"] == "warning"
    assert f"/admin/guided-sessions/{session.id}" in dispatcher.calls[0]["message"]
    assert "Pour water." in dispatcher.calls[0]["message"]


@pytest.mark.asyncio
async def test_emergency_uses_all_channels_including_ha_speaker(db_session, db_factory) -> None:
    session = _seed(db_session, channels=["telegram"])
    dispatcher = _Dispatcher()
    escalator = FullEscalator(dispatcher, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="hazard_active", emergency=True)

    assert dispatcher.calls[0]["alert_level"] == "emergency"
    assert dispatcher.calls[0]["rule_config"]["channels"] == ["telegram", "ha_speaker_tts"]
    assert "hazard" in dispatcher.calls[0]["message"]


@pytest.mark.asyncio
async def test_escalate_broadcasts_ws_event(db_session, db_factory) -> None:
    session = _seed(db_session)
    ws = _WsManager()
    escalator = FullEscalator(
        _Dispatcher(),
        db_factory=db_factory,
        ws_manager=ws,
        settings=_settings(),
    )

    await escalator.escalate(session=session, reason="stuck", emergency=False)

    assert ws.broadcasts[0]["type"] == "guided_escalation"
    assert ws.broadcasts[0]["session_id"] == session.id
    assert ws.broadcasts[0]["takeover_url"] == f"/admin/guided-sessions/{session.id}"


@pytest.mark.asyncio
async def test_escalation_unanswered_after_grace_abandons_and_resumes(
    db_session, db_factory
) -> None:
    session = _seed(db_session, execution_id=123)
    clock = _Clock()
    pipeline = _PipelineExecutor()
    service = GuidedTaskService(
        db_factory=db_factory,
        pipeline_executor=pipeline,
        settings=_settings(),
        time_fn=clock,
    )
    db_session.query(GuidedSession).filter(GuidedSession.id == session.id).update(
        {
            "status": "escalated",
            "last_activity_at": clock.now - timedelta(seconds=1801),
        }
    )
    db_session.commit()

    await service.tick(clock.now)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.status == "abandoned"
    assert stored.outcome == "escalated_unanswered"
    assert pipeline.resumed == [123]


@pytest.mark.asyncio
async def test_channel_override_precedence(db_session, db_factory) -> None:
    session = _seed(db_session, channels=["pwa_popup_text"])
    dispatcher = _Dispatcher()
    escalator = FullEscalator(dispatcher, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="stuck", emergency=False)

    assert dispatcher.calls[0]["rule_config"]["channels"] == ["pwa_popup_text"]


@pytest.mark.asyncio
async def test_missing_dispatcher_graceful(db_session, db_factory) -> None:
    session = _seed(db_session)
    escalator = FullEscalator(None, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="stuck", emergency=False)

    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).status == "escalated"
    event = db_session.query(GuidedSessionEvent).filter_by(session_id=session.id).one()
    assert event.kind == "escalation"
