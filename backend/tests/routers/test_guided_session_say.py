from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.models.conversation import ConversationTurn
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.routers import guided_sessions
from backend.routers.dependencies import get_guided_task_service
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
        self.prompts.append(
            {
                "prompt": prompt,
                "callback": callback,
                "ttl_seconds": ttl_seconds,
                "voice_instruction": voice_instruction,
                "metadata": metadata,
            }
        )

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
                "escalation_channels": ["telegram"],
            }
        }
    )


def _seed(db_session, *, status: str = "escalated") -> GuidedSession:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(
        name="Make tea",
        person_id="resident-1",
        is_enabled=True,
        system_instruction_override="Speak in Tamil.",
    )
    db_session.add(routine)
    db_session.flush()
    db_session.add(RoutineStep(routine_id=routine.id, ord=0, prompt_template="Pour water."))
    session = GuidedSession(
        routine_id=routine.id,
        person_id="resident-1",
        status=status,
        current_step_ord=0,
        attempts=0,
        started_at=datetime(2026, 6, 17, 12, 0, tzinfo=UTC),
        last_activity_at=datetime(2026, 6, 17, 12, 5, tzinfo=UTC),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


def _client(db_factory, service: GuidedTaskService, auth: AuthContext | None = None) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.guided_task_service = service
    app.include_router(guided_sessions.router, prefix="/api/v1")
    app.dependency_overrides[get_guided_task_service] = lambda: service
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def _caregiver() -> AuthContext:
    return AuthContext(
        key="caregiver",
        name="Caregiver",
        permissions=["guided_sessions:read", "guided_sessions:takeover"],
    )


@pytest.mark.asyncio
async def test_say_records_caregiver_turn(db_session, db_factory) -> None:
    session = _seed(db_session)
    manager = ConversationManager(db_factory)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=manager,
        ws_manager=_WsManager(),
        settings=_settings(),
    )
    client = _client(db_factory, service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/say", json={"text": "Try now"})

    assert response.status_code == 200
    turn = db_session.query(ConversationTurn).one()
    assert turn.actor == "caregiver"
    assert turn.content == "Try now"
    assert turn.metadata_json["guided_session_id"] == session.id


@pytest.mark.asyncio
async def test_say_injects_orchestrator_prompt(db_session, db_factory) -> None:
    session = _seed(db_session)
    ws = _WsManager()
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=ConversationManager(db_factory),
        ws_manager=ws,
        settings=_settings(),
    )
    client = _client(db_factory, service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/say", json={"text": "Try now"})

    assert response.status_code == 200
    assert ws.prompts[0]["metadata"]["actor"] == "caregiver"
    assert ws.prompts[0]["metadata"]["delivery_type"] == "guided_task_start"
    assert ws.prompts[0]["metadata"]["session_id"] == session.id


@pytest.mark.asyncio
async def test_say_emits_caregiver_message_event(db_session, db_factory) -> None:
    session = _seed(db_session)
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=ConversationManager(db_factory),
        ws_manager=_WsManager(),
        settings=_settings(),
    )
    client = _client(db_factory, service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/say", json={"text": "Try now"})

    assert response.status_code == 200
    event = db_session.query(GuidedSessionEvent).filter_by(kind="caregiver_message").one()
    assert event.actor == "caregiver"
    assert event.detail == {"text": "Try now"}


def test_say_requires_caregiver_permission(db_session, db_factory) -> None:
    session = _seed(db_session)
    service = GuidedTaskService(db_factory=db_factory, settings=_settings())
    client = _client(db_factory, service)

    response = client.post(f"/api/v1/guided-sessions/{session.id}/say", json={"text": "Try now"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_her_ui_never_receives_caregiver_text(db_session, db_factory) -> None:
    session = _seed(db_session)
    ws = _WsManager()
    service = GuidedTaskService(
        db_factory=db_factory,
        conversation_manager=ConversationManager(db_factory),
        ws_manager=ws,
        settings=_settings(),
    )
    client = _client(db_factory, service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/say", json={"text": "Try now"})

    assert response.status_code == 200
    metadata = ws.prompts[0]["metadata"]
    assert metadata["delivery_type"] == "guided_task_start"
    assert metadata["caregiver_text_hidden"] is True
