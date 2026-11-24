"""The activity and zone shapes the editors save are the shapes the evaluators read.

The schema tests prove the normalizer's output; these prove the runtime acts on
it, end to end, so the editor/evaluator drift cannot come back silently.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.models.guided_task import GuidedSession, RoutineStep
from backend.models.person import HouseholdMember
from backend.routers import routines
from backend.routers.dependencies import get_guided_task_service
from backend.schemas.guided_task import RoutineStepIn
from backend.services.guided_task.completion.response import build_evaluators
from backend.services.guided_task.service import GuidedTaskService

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


@dataclass
class _ActivityService:
    rows: list = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    async def query_in_window(self, **kwargs):
        self.calls.append(kwargs)
        return self.rows


@dataclass
class _ZoneService:
    zone_id: int

    async def current_zone(self, person_id: str):
        return SimpleNamespace(id=self.zone_id)


def _saved_gate(gate: dict) -> dict:
    return RoutineStepIn(ord=0, prompt_template="p", completion_gate=gate).completion_gate


def _evaluator(gate: dict, kind: str, **services):
    return next(e for e in build_evaluators(gate, **services) if e.kind == kind)


@pytest.mark.asyncio
async def test_saved_activity_window_is_the_window_queried() -> None:
    gate = _saved_gate(
        {"kinds": ["activity_signal"], "activity": {"activity_type": "cooking", "window_s": 300}}
    )
    activity = _ActivityService()

    await _evaluator(gate, "activity_signal", activity_service=activity).is_complete(
        session=SimpleNamespace(id=1, person_id="resident-1"),
        step=SimpleNamespace(zone_id=None),
        evidence={"now": NOW},
    )

    [call] = activity.calls
    assert call["activity_type"] == "cooking"
    assert call["window_start"] == NOW - timedelta(minutes=5)


@pytest.mark.asyncio
async def test_saved_zone_target_wins_over_the_step_zone() -> None:
    gate = _saved_gate({"kinds": ["zone_presence"], "zone": {"zone_id": 5}})
    step = SimpleNamespace(zone_id=7)
    session = SimpleNamespace(id=1, person_id="resident-1")

    in_target = await _evaluator(gate, "zone_presence", zone_service=_ZoneService(5)).is_complete(
        session=session, step=step, evidence={}
    )
    in_step_zone = await _evaluator(
        gate, "zone_presence", zone_service=_ZoneService(7)
    ).is_complete(session=session, step=step, evidence={})

    assert in_target.complete is True
    assert in_step_zone.complete is False


def test_activity_skip_saved_through_the_router_skips_on_entry(db_session, db_factory) -> None:
    """The router stores the python-mode dump (an enum member), not a JSON dump."""
    db_session.add(HouseholdMember(id="resident-1", name="Ruth"))
    db_session.commit()
    activity = _ActivityService(rows=[{"activity_type": "medication"}])
    service = GuidedTaskService(
        db_factory=db_factory,
        activity_service=activity,
        settings=Settings.from_dict(
            {"guided_task": {"step_timeout_s": 300, "max_step_attempts": 3, "resume_grace_s": 600}}
        ),
        time_fn=lambda: NOW,
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(routines.router, prefix="/api/v1")
    app.dependency_overrides[get_guided_task_service] = lambda: service
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="admin", name="Admin", roles=["admin"]
    )
    client = TestClient(app, raise_server_exceptions=False)

    routine_id = client.post(
        "/api/v1/routines", json={"name": "Pills", "person_id": "resident-1"}
    ).json()["id"]
    saved = client.put(
        f"/api/v1/routines/{routine_id}/steps",
        json={
            "steps": [
                {
                    "ord": 0,
                    "prompt_template": "Take your pills.",
                    "skip_condition": {
                        "kind": "activity_signal",
                        "activity_type": "medication",
                        "window_minutes": 30,
                    },
                },
                {"ord": 1, "prompt_template": "Drink some water."},
            ]
        },
    )
    assert saved.status_code == 200
    db_session.expire_all()
    stored = db_session.query(RoutineStep).filter_by(routine_id=routine_id, ord=0).one()
    assert stored.skip_condition == {
        "kind": "activity_signal",
        "activity_type": "medication",
        "window_minutes": 30.0,
    }

    session = asyncio.run(service.start(routine_id, "resident-1"))

    db_session.expire_all()
    assert db_session.get(GuidedSession, session.id).current_step_ord == 1
    assert activity.calls[0]["activity_type"] == "medication"
    assert activity.calls[0]["window_start"] == NOW - timedelta(minutes=30)
