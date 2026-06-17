from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.guided_task.escalation.minimal import NotifyOnlyEscalator


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        channels = kwargs["rule_config"]["channels"]
        return dict.fromkeys(channels, True)


def _settings() -> Settings:
    return Settings.from_dict(
        {"guided_task": {"escalation_channels": ["telegram", "pwa_popup_text"]}}
    )


def _seed(db_session, *, channels: list[str] | None = None) -> GuidedSession:
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
    db_session.add(
        RoutineStep(routine_id=routine.id, ord=0, prompt_template="Pour water.")
    )
    session = GuidedSession(
        routine_id=routine.id,
        person_id="resident-1",
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
async def test_escalate_sets_status_and_emits_event(db_session, db_factory) -> None:
    session = _seed(db_session)
    dispatcher = _Dispatcher()
    escalator = NotifyOnlyEscalator(dispatcher, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="resident_requested", emergency=False)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    event = (
        db_session.query(GuidedSessionEvent)
        .filter(GuidedSessionEvent.session_id == session.id)
        .filter(GuidedSessionEvent.kind == "escalation")
        .one()
    )
    assert stored.status == "escalated"
    assert event.detail == {"reason": "resident_requested", "emergency": False}


@pytest.mark.asyncio
async def test_escalate_sends_on_routine_channel_override_then_global(
    db_session, db_factory
) -> None:
    session = _seed(db_session, channels=["telegram"])
    dispatcher = _Dispatcher()
    escalator = NotifyOnlyEscalator(dispatcher, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="stuck", emergency=False)

    assert dispatcher.calls[0]["rule_config"]["channels"] == ["telegram"]


@pytest.mark.asyncio
async def test_emergency_adds_ha_speaker_channel(db_session, db_factory) -> None:
    session = _seed(db_session)
    dispatcher = _Dispatcher()
    escalator = NotifyOnlyEscalator(dispatcher, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="hazard", emergency=True)

    assert dispatcher.calls[0]["alert_level"] == "emergency"
    assert "ha_speaker_tts" in dispatcher.calls[0]["rule_config"]["channels"]


@pytest.mark.asyncio
async def test_missing_dispatcher_is_graceful(db_session, db_factory) -> None:
    session = _seed(db_session)
    escalator = NotifyOnlyEscalator(None, db_factory=db_factory, settings=_settings())

    await escalator.escalate(session=session, reason="stuck", emergency=False)

    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).status == "escalated"
