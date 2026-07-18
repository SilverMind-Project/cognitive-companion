"""M24: guided sessions link to a real conversation_sessions row.

Regression coverage for the primary-key collision closed by M24 (G2):
guided session ids and conversation session ids are independent autoincrement
sequences, and guided-task code must never key ConversationManager reads or
writes by a guided session id.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.core.config import Settings
from backend.models.conversation import ConversationSession, ConversationTurn
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.conversation_manager import ConversationManager
from backend.services.guided_task.escalation.full import FullEscalator
from backend.services.guided_task.service import GuidedTaskService


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def dispatch(self, **kwargs) -> dict[str, bool]:
        self.calls.append(kwargs)
        return dict.fromkeys(kwargs["rule_config"]["channels"], True)


def _settings() -> Settings:
    return Settings.from_dict(
        {
            "app": {"timezone": "America/New_York"},
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": 3,
                "resume_grace_s": 600,
                "transcript_retention_days": 30,
                "summon_channels": ["pwa_popup_text"],
                "escalation_channels": ["telegram"],
            },
        }
    )


def _seed_routine(db_session, *, person_id: str = "resident-1") -> int:
    if db_session.get(HouseholdMember, person_id) is None:
        db_session.add(HouseholdMember(id=person_id, name="Resident"))
        db_session.flush()
    routine = Routine(name="Make tea", person_id=person_id, is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    db_session.add(
        RoutineStep(
            routine_id=routine.id,
            ord=0,
            prompt_template="Pour water.",
            completion_gate={"kinds": ["response"]},
            is_safety_critical=False,
        )
    )
    db_session.commit()
    return routine.id


def _seed_session(
    db_session,
    routine_id: int,
    *,
    status: str,
    person_id: str = "resident-1",
    conversation_session_id: int | None = None,
) -> GuidedSession:
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    session = GuidedSession(
        routine_id=routine_id,
        person_id=person_id,
        status=status,
        current_step_ord=0,
        attempts=0,
        started_at=now,
        last_activity_at=now,
        conversation_session_id=conversation_session_id,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.mark.asyncio
async def test_on_session_opened_links_conversation(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    session = _seed_session(db_session, routine_id, status="summoning")
    conversation_manager = ConversationManager(db_factory)
    conversation_id = conversation_manager.create_session()
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    await service.on_session_opened(conversation_id)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.conversation_session_id == conversation_id
    event = (
        db_session.query(GuidedSessionEvent)
        .filter_by(session_id=session.id, kind="conversation_linked")
        .one()
    )
    assert event.actor == "system"
    assert event.detail == {"conversation_session_id": conversation_id}


@pytest.mark.asyncio
async def test_on_session_opened_does_not_relink_already_linked_session(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    conversation_manager = ConversationManager(db_factory)
    existing_conversation_id = conversation_manager.create_session()
    session = _seed_session(
        db_session,
        routine_id,
        status="active",
        conversation_session_id=existing_conversation_id,
    )
    new_conversation_id = conversation_manager.create_session()
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    await service.on_session_opened(new_conversation_id)

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    assert stored.conversation_session_id == existing_conversation_id
    assert (
        db_session.query(GuidedSessionEvent)
        .filter_by(session_id=session.id, kind="conversation_linked")
        .count()
        == 0
    )


@pytest.mark.asyncio
async def test_caregiver_say_uses_linked_conversation(db_session, db_factory):
    routine1_id = _seed_routine(db_session)
    _seed_session(db_session, routine1_id, status="active")
    routine2_id = _seed_routine(db_session)
    session2 = _seed_session(db_session, routine2_id, status="escalated")
    conversation_manager = ConversationManager(db_factory)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    await service.caregiver_say(session2.id, "please try again")

    db_session.expire_all()
    stored = db_session.get(GuidedSession, session2.id)
    conversation_id = stored.conversation_session_id
    assert conversation_id is not None
    # The collision regression: session2's own id must never have been used
    # as the conversation id (the old ensure_session(session.id) bug).
    assert db_session.get(ConversationSession, session2.id) is None

    turn = db_session.query(ConversationTurn).filter_by(session_id=conversation_id).one()
    assert turn.actor == "caregiver"
    assert turn.content == "please try again"


@pytest.mark.asyncio
async def test_caregiver_say_without_realtime_creates_via_sequence(db_session, db_factory):
    routine1_id = _seed_routine(db_session)
    session1 = _seed_session(db_session, routine1_id, status="escalated")
    routine2_id = _seed_routine(db_session)
    session2 = _seed_session(db_session, routine2_id, status="caregiver_takeover")
    conversation_manager = ConversationManager(db_factory)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    await service.caregiver_say(session1.id, "hello one")
    await service.caregiver_say(session2.id, "hello two")

    # Must not raise IntegrityError: the old ensure_session(guided_id) path
    # inserted explicit PKs without advancing the sequence, so a later
    # autoincrement create_session() could collide once the sequence caught up.
    new_id = conversation_manager.create_session()
    assert new_id is not None


@pytest.mark.asyncio
async def test_escalation_transcript_contains_resident_turns(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    conversation_manager = ConversationManager(db_factory)
    conversation_id = conversation_manager.create_session()
    conversation_manager.add_turn(conversation_id, "user", "I finished the tea")
    conversation_manager.add_turn(conversation_id, "assistant", "Wonderful, well done")
    session = _seed_session(
        db_session, routine_id, status="active", conversation_session_id=conversation_id
    )
    dispatcher = _Dispatcher()
    escalator = FullEscalator(
        dispatcher,
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
    )

    await escalator.escalate(session=session, reason="attempts_exhausted", emergency=False)

    message = dispatcher.calls[0]["message"]
    assert "I finished the tea" in message
    assert "Wonderful, well done" in message


@pytest.mark.asyncio
async def test_retention_prunes_only_linked_conversations(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    old_started = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    old_session = GuidedSession(
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
    db_session.add(old_session)
    db_session.flush()
    old_session_id = old_session.id

    # An unrelated realtime conversation whose id happens to equal the
    # pruned guided session's id: it must survive because it was never
    # linked to that guided session.
    unrelated_conversation = ConversationSession(id=old_session_id)
    db_session.add(unrelated_conversation)
    db_session.commit()

    conversation_manager = ConversationManager(db_factory)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    result = await service.prune_retained_data()

    assert result["sessions"] == 1
    assert result["transcript_sessions"] == 0
    db_session.expire_all()
    assert db_session.get(GuidedSession, old_session_id) is None
    assert db_session.get(ConversationSession, old_session_id) is not None


@pytest.mark.asyncio
async def test_retention_prunes_linked_conversation(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    conversation_manager = ConversationManager(db_factory)
    conversation_id = conversation_manager.create_session()
    old_started = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    old_session = GuidedSession(
        routine_id=routine_id,
        person_id="resident-1",
        status="completed",
        current_step_ord=0,
        attempts=0,
        started_at=old_started,
        last_activity_at=old_started,
        completed_at=old_started + timedelta(minutes=5),
        outcome="completed",
        conversation_session_id=conversation_id,
    )
    db_session.add(old_session)
    db_session.commit()
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    result = await service.prune_retained_data()

    assert result["sessions"] == 1
    assert result["transcript_sessions"] == 1
    db_session.expire_all()
    assert db_session.get(ConversationSession, conversation_id) is None


@pytest.mark.asyncio
async def test_get_detail_reads_transcript_via_linkage(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    conversation_manager = ConversationManager(db_factory)
    conversation_id = conversation_manager.create_session()
    conversation_manager.add_turn(conversation_id, "user", "I finished the tea")
    session = _seed_session(
        db_session, routine_id, status="active", conversation_session_id=conversation_id
    )
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    detail = await service.get_detail(session.id)

    assert [turn.content for turn in detail.recent_transcript] == ["I finished the tea"]


@pytest.mark.asyncio
async def test_get_detail_transcript_empty_when_unlinked(db_session, db_factory):
    routine_id = _seed_routine(db_session)
    session = _seed_session(db_session, routine_id, status="active")
    conversation_manager = ConversationManager(db_factory)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    detail = await service.get_detail(session.id)

    assert detail.recent_transcript == []


@pytest.mark.asyncio
async def test_retention_never_prunes_a_conversation_linked_to_a_live_session(
    db_session, db_factory
):
    conversation_manager = ConversationManager(db_factory)
    conversation_id = conversation_manager.create_session()

    routine1_id = _seed_routine(db_session)
    old_started = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    old_session = GuidedSession(
        routine_id=routine1_id,
        person_id="resident-1",
        status="completed",
        current_step_ord=0,
        attempts=0,
        started_at=old_started,
        last_activity_at=old_started,
        completed_at=old_started + timedelta(minutes=5),
        outcome="completed",
        conversation_session_id=conversation_id,
    )
    db_session.add(old_session)
    routine2_id = _seed_routine(db_session, person_id="resident-2")
    # Same conversation is still in use by a live session (e.g. she started a
    # second routine in the same realtime conversation).
    _seed_session(
        db_session,
        routine2_id,
        status="active",
        person_id="resident-2",
        conversation_session_id=conversation_id,
    )
    db_session.commit()
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=conversation_manager,
        settings=_settings(),
        time_fn=_Clock(),
    )

    result = await service.prune_retained_data()

    assert result["sessions"] == 1
    assert result["transcript_sessions"] == 0
    db_session.expire_all()
    assert db_session.get(ConversationSession, conversation_id) is not None
