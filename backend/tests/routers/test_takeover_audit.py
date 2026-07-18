from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from backend.core.config import Settings
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.services.conversation_manager import ConversationManager
from backend.services.guided_task.service import GuidedTaskService


@dataclass
class _WsManager:
    prompts: list[dict] = field(default_factory=list)
    broadcasts: list[dict] = field(default_factory=list)

    async def send_backend_task(
        self,
        prompt: str,
        callback=None,
        ttl_seconds: int = 300,
        *,
        voice_instruction: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.prompts.append({"prompt": prompt, "metadata": metadata})

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)


def _settings() -> Settings:
    return Settings.from_dict(
        {
            "guided_task": {
                "step_timeout_s": 300,
                "max_step_attempts": 3,
                "resume_grace_s": 600,
                "escalation_grace_s": 1800,
            }
        }
    )


def _seed(db_session) -> GuidedSession:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    for ord_ in range(2):
        db_session.add(RoutineStep(routine_id=routine.id, ord=ord_, prompt_template=f"Step {ord_}"))
    session = GuidedSession(
        routine_id=routine.id,
        person_id="resident-1",
        status="escalated",
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
async def test_full_takeover_produces_attributed_event_trail(db_session, db_factory) -> None:
    session = _seed(db_session)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=ConversationManager(db_factory),
        ws_manager=_WsManager(),
        settings=_settings(),
    )

    await service.begin_takeover(session.id)
    await service.caregiver_say(session.id, "Please pour the water.")
    await service.caregiver_advance(session.id)
    await service.release_takeover(session.id)

    events = (
        db_session.query(GuidedSessionEvent)
        .filter(GuidedSessionEvent.session_id == session.id)
        .order_by(GuidedSessionEvent.id)
        .all()
    )
    trail = [(event.kind, event.actor) for event in events]
    # caregiver_say links a conversation on demand when none is open yet
    # (M24, D18: GuidedTaskService._link_conversation), so the first
    # caregiver message is preceded by a system-attributed conversation_linked
    # event.
    assert trail == [
        ("takeover_started", "caregiver"),
        ("conversation_linked", "system"),
        ("caregiver_message", "caregiver"),
        ("step_completed", "caregiver"),
        ("step_entered", "caregiver"),
        ("takeover_ended", "caregiver"),
    ]
