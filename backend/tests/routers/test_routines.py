"""Router tests for the routines CRUD + step-replace endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.models.person import HouseholdMember
from backend.routers import routines
from backend.routers.dependencies import get_guided_task_service
from backend.services.guided_task.service import GuidedTaskService


@dataclass
class _WsManager:
    broadcasts: list[dict] = field(default_factory=list)

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)

    @property
    def has_connections(self) -> bool:
        return False


def _settings_dict() -> dict:
    return {
        "guided_task": {
            "step_timeout_s": 300,
            "max_step_attempts": 3,
            "resume_grace_s": 600,
            "escalation_grace_s": 1800,
            "escalation_channels": ["telegram"],
        }
    }


def _seed_member(db_session) -> HouseholdMember:
    member = HouseholdMember(id="resident-1", name="Resident")
    db_session.add(member)
    db_session.commit()
    return member


def _client(db_factory, auth: AuthContext | None = None) -> TestClient:
    from backend.core.config import Settings

    app = FastAPI()
    register_exception_handlers(app)
    svc = GuidedTaskService(
        db_factory=db_factory,
        ws_manager=_WsManager(),
        settings=Settings.from_dict(_settings_dict()),
    )
    app.state.guided_task_service = svc
    app.include_router(routines.router, prefix="/api/v1")
    app.dependency_overrides[get_guided_task_service] = lambda: svc
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def _admin() -> AuthContext:
    return AuthContext(key="admin", name="Admin", permissions=["admin"])


def test_crud_roundtrip(db_factory, db_session) -> None:
    _seed_member(db_session)
    client = _client(db_factory, _admin())

    created = client.post(
        "/api/v1/routines",
        json={"name": "Make Tea", "person_id": "resident-1"},
    )
    assert created.status_code == 201
    routine_id = created.json()["id"]
    assert created.json()["name"] == "Make Tea"

    listed = client.get("/api/v1/routines")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["name"] == "Make Tea"

    detail = client.get(f"/api/v1/routines/{routine_id}")
    assert detail.status_code == 200
    assert detail.json()["routine"]["id"] == routine_id
    assert detail.json()["steps"] == []

    patched = client.patch(f"/api/v1/routines/{routine_id}", json={"name": "Brew Tea"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Brew Tea"

    deleted = client.delete(f"/api/v1/routines/{routine_id}")
    assert deleted.status_code == 204

    after_delete = client.get(f"/api/v1/routines/{routine_id}")
    assert after_delete.status_code == 404


def test_list_filter_by_person(db_factory, db_session) -> None:
    db_session.add(HouseholdMember(id="resident-1", name="A"))
    db_session.add(HouseholdMember(id="resident-2", name="B"))
    db_session.commit()

    client = _client(db_factory, _admin())
    client.post("/api/v1/routines", json={"name": "Routine A", "person_id": "resident-1"})
    client.post("/api/v1/routines", json={"name": "Routine B", "person_id": "resident-2"})

    resp = client.get("/api/v1/routines?person_id=resident-1")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["name"] == "Routine A"


def test_step_replace_roundtrip(db_factory, db_session) -> None:
    _seed_member(db_session)
    client = _client(db_factory, _admin())

    created = client.post(
        "/api/v1/routines",
        json={"name": "Make Tea", "person_id": "resident-1"},
    )
    routine_id = created.json()["id"]

    steps_payload = {
        "steps": [
            {
                "ord": 0,
                "prompt_template": "Fill the kettle.",
                "completion_gate": {"kinds": ["response"]},
            },
            {
                "ord": 1,
                "prompt_template": "Boil the water.",
                "completion_gate": {"kinds": ["response"]},
            },
        ]
    }
    replaced = client.put(f"/api/v1/routines/{routine_id}/steps", json=steps_payload)
    assert replaced.status_code == 200
    data = replaced.json()
    assert len(data["steps"]) == 2
    assert data["steps"][0]["ord"] == 0
    assert data["steps"][1]["ord"] == 1
    assert data["routine"]["step_count"] == 2

    detail = client.get(f"/api/v1/routines/{routine_id}")
    assert detail.json()["routine"]["step_count"] == 2


def test_step_replace_rejects_non_contiguous_ord(db_factory, db_session) -> None:
    _seed_member(db_session)
    client = _client(db_factory, _admin())

    created = client.post(
        "/api/v1/routines",
        json={"name": "Make Tea", "person_id": "resident-1"},
    )
    routine_id = created.json()["id"]

    bad_steps = {
        "steps": [
            {"ord": 0, "prompt_template": "Step 0."},
            {"ord": 2, "prompt_template": "Step 2."},
        ]
    }
    resp = client.put(f"/api/v1/routines/{routine_id}/steps", json=bad_steps)
    assert resp.status_code == 422


def test_step_replace_rejects_duplicate_ord(db_factory, db_session) -> None:
    _seed_member(db_session)
    client = _client(db_factory, _admin())

    created = client.post(
        "/api/v1/routines",
        json={"name": "Make Tea", "person_id": "resident-1"},
    )
    routine_id = created.json()["id"]

    dup_steps = {
        "steps": [
            {"ord": 0, "prompt_template": "Step A."},
            {"ord": 0, "prompt_template": "Step B."},
        ]
    }
    resp = client.put(f"/api/v1/routines/{routine_id}/steps", json=dup_steps)
    assert resp.status_code == 422


def test_auth_rejection(db_factory) -> None:
    client = _client(db_factory)

    responses = [
        client.get("/api/v1/routines"),
        client.post("/api/v1/routines", json={"name": "x", "person_id": "y"}),
        client.get("/api/v1/routines/1"),
        client.patch("/api/v1/routines/1", json={"name": "x"}),
        client.delete("/api/v1/routines/1"),
        client.put("/api/v1/routines/1/steps", json={"steps": []}),
        client.post("/api/v1/routines/1/test-run", json={}),
    ]
    for resp in responses:
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code} for {resp.url}"


def test_test_run_starts_session_without_presence_check(db_factory, db_session) -> None:
    _seed_member(db_session)
    client = _client(db_factory, _admin())

    created = client.post(
        "/api/v1/routines",
        json={"name": "Make Tea", "person_id": "resident-1"},
    )
    routine_id = created.json()["id"]

    client.put(
        f"/api/v1/routines/{routine_id}/steps",
        json={"steps": [{"ord": 0, "prompt_template": "Fill kettle."}]},
    )

    test_run = client.post(f"/api/v1/routines/{routine_id}/test-run", json={})
    assert test_run.status_code == 201
    session_data = test_run.json()
    assert session_data["routine_id"] == routine_id
    assert session_data["person_id"] == "resident-1"
    assert session_data["status"] in ("active", "waiting", "summoning", "pending")
