from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.models.guided_task import GuidedSession, GuidedSessionEvent, Routine, RoutineStep
from backend.models.person import HouseholdMember
from backend.routers import guided_sessions
from backend.routers.dependencies import get_guided_task_service
from backend.services.guided_task.service import GuidedTaskService


class _SchedulerBackend:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def add_job(self, finalize, trigger, run_date, id, args, replace_existing):
        self.jobs.append(
            {
                "finalize": finalize,
                "trigger": trigger,
                "run_date": run_date,
                "id": id,
                "args": args,
                "replace_existing": replace_existing,
            }
        )


@dataclass
class _Scheduler:
    apscheduler: _SchedulerBackend = field(default_factory=_SchedulerBackend)


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


def _seed(db_session, *, status: str = "escalated", steps: int = 2) -> GuidedSession:
    db_session.add(HouseholdMember(id="resident-1", name="Resident"))
    db_session.flush()
    routine = Routine(name="Make tea", person_id="resident-1", is_enabled=True)
    db_session.add(routine)
    db_session.flush()
    for ord_ in range(steps):
        db_session.add(RoutineStep(routine_id=routine.id, ord=ord_, prompt_template=f"Step {ord_}"))
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


def _client(service: GuidedTaskService, auth: AuthContext | None = None) -> TestClient:
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


def test_takeover_sets_status_and_pauses_timeout(db_session, db_factory) -> None:
    session = _seed(db_session, status="escalated")
    service = GuidedTaskService(db_factory=db_factory, settings=_settings())
    client = _client(service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/takeover")

    assert response.status_code == 200
    assert response.json()["status"] == "caregiver_takeover"
    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).status == "caregiver_takeover"


@pytest.mark.asyncio
async def test_on_step_timeout_noop_during_takeover(db_session, db_factory) -> None:
    session = _seed(db_session, status="caregiver_takeover")
    service = GuidedTaskService(db_factory=db_factory, settings=_settings())

    decision = await service.on_step_timeout(session.id)

    assert decision.kind == "noop"
    assert decision.reason == "caregiver_takeover_paused"


def test_advance_marks_step_complete_with_caregiver_actor(db_session, db_factory) -> None:
    session = _seed(db_session, status="caregiver_takeover")
    service = GuidedTaskService(db_factory=db_factory, settings=_settings())
    client = _client(service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/advance")

    assert response.status_code == 200
    db_session.expire_all()
    stored = db_session.get(GuidedSession, session.id)
    event = db_session.query(GuidedSessionEvent).filter_by(kind="step_completed").one()
    assert stored.current_step_ord == 1
    assert event.actor == "caregiver"
    assert event.detail == {"confirmed": True, "source": "caregiver"}


def test_complete_finalizes_with_escalated_resolved(db_session, db_factory) -> None:
    session = _seed(db_session, status="caregiver_takeover")
    service = GuidedTaskService(db_factory=db_factory, settings=_settings())
    client = _client(service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/complete")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["outcome"] == "escalated_resolved"


def test_release_returns_to_active_and_rearms_timeout(db_session, db_factory) -> None:
    session = _seed(db_session, status="caregiver_takeover")
    scheduler = _Scheduler()
    service = GuidedTaskService(db_factory=db_factory, scheduler=scheduler, settings=_settings())
    client = _client(service, _caregiver())

    response = client.post(f"/api/v1/guided-sessions/{session.id}/release")

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert scheduler.apscheduler.jobs[0]["id"] == f"guided_session_timeout_{session.id}"


def test_takeover_endpoints_require_permission(db_session, db_factory) -> None:
    session = _seed(db_session, status="escalated")
    service = GuidedTaskService(db_factory=db_factory, settings=_settings())
    client = _client(service)

    response = client.post(f"/api/v1/guided-sessions/{session.id}/takeover")

    assert response.status_code == 401


def test_auth_yaml_covers_takeover_routes() -> None:
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    permission_map = data["permission_map"]

    assert "GET /api/v1/guided-sessions/*/detail" in permission_map["guided_sessions:read"]
    for action in ["takeover", "say", "advance", "complete", "release"]:
        assert (
            f"POST /api/v1/guided-sessions/*/{action}" in permission_map["guided_sessions:takeover"]
        )
    assert "guided_sessions:takeover" in permission_map["caregiver"]
