"""Router tests for gate-graph CRUD, validation, presets, and test-run (VG08)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule
from backend.routers import gate_graphs
from backend.services import rule_service
from backend.services.guided_task.gate_presets import build_default_vlm_gate


@dataclass
class _FakeVerdict:
    complete: bool = True
    confidence: float = 0.82
    reason: str = "looks done"
    node_results: dict | None = None
    cost: dict | None = None
    profile: str = "confirm"

    def __post_init__(self) -> None:
        if self.node_results is None:
            self.node_results = {"llm_call_1": {"complete": True}}
        if self.cost is None:
            self.cost = {"model_calls": 1, "frames": 3, "latency_ms": 12}


class _FakeGuidedService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run_gate_preview(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeVerdict()


def _client(
    db_session,
    auth: AuthContext | None = None,
    guided_service: _FakeGuidedService | None = None,
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    if guided_service is not None:
        app.state.guided_task_service = guided_service
    app.include_router(gate_graphs.router, prefix="/api/v1")
    app.include_router(gate_graphs.presets_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def _admin() -> AuthContext:
    return AuthContext(key="admin", name="Admin", permissions=["admin"])


def _reader() -> AuthContext:
    return AuthContext(key="r", name="Reader", permissions=["gate_graphs:read"])


def _seed_normal_rule(db_session, name: str = "Normal Rule") -> Rule:
    rule = Rule(name=name, enabled=True, trigger_types=["sensor_event"])
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


# -- list --------------------------------------------------------------------


def test_list_returns_only_callable_rules(db_session) -> None:
    _seed_normal_rule(db_session)
    build_default_vlm_gate(db_session, name="Gate A")
    db_session.commit()

    resp = _client(db_session, _admin()).get("/api/v1/gate-graphs")
    assert resp.status_code == 200
    body = resp.json()
    names = [item["name"] for item in body["items"]]
    assert names == ["Gate A"]
    assert body["total"] == 1


def test_gate_graph_list_uses_rule_service(db_session, monkeypatch) -> None:
    """Parity: the router delegates to the shared rule service, not a bespoke query."""
    calls: list[dict] = []
    original = rule_service.list_rules

    def spy(db, *, callable_only=None):
        calls.append({"callable_only": callable_only})
        return original(db, callable_only=callable_only)

    monkeypatch.setattr(rule_service, "list_rules", spy)
    resp = _client(db_session, _admin()).get("/api/v1/gate-graphs")
    assert resp.status_code == 200
    assert calls == [{"callable_only": True}]


# -- create ------------------------------------------------------------------


def test_create_blank_sets_empty_trigger_types(db_session) -> None:
    resp = _client(db_session, _admin()).post(
        "/api/v1/gate-graphs", json={"name": "Blank Gate"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["trigger_types"] == []
    rule = db_session.get(Rule, body["id"])
    assert rule.is_callable


def test_create_from_preset_clones_steps_edges(db_session) -> None:
    resp = _client(db_session, _admin()).post(
        "/api/v1/gate-graphs",
        json={"name": "My Kettle", "from_preset": "kettle_on_hob"},
    )
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    steps = db_session.query(PipelineStep).filter(PipelineStep.rule_id == rule_id).all()
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == rule_id).all()
    step_types = {s.step_type for s in steps}
    assert "gate_verdict" in step_types
    assert "llm_call" in step_types
    assert len(edges) >= 4  # poll->scene->cond, cond--true-->llm, cond--false-->verdict, llm->verdict


def test_create_from_unknown_preset_404(db_session) -> None:
    resp = _client(db_session, _admin()).post(
        "/api/v1/gate-graphs", json={"name": "X", "from_preset": "nope"}
    )
    assert resp.status_code == 404


# -- validate ----------------------------------------------------------------


def test_validate_reports_missing_verdict_and_non_gate_safe(db_session) -> None:
    rule = Rule(name="Bad Gate", enabled=True, trigger_types=[])
    db_session.add(rule)
    db_session.flush()
    # notification is a side-effecting step: not gate_safe, and there is no verdict.
    db_session.add(
        PipelineStep(
            rule_id=rule.id, order=0, step_type="notification", label="notify_1",
            config_json={}, enabled=True,
        )
    )
    db_session.commit()

    resp = _client(db_session, _admin()).post(f"/api/v1/gate-graphs/{rule.id}/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    joined = " ".join(body["errors"])
    assert "non-gate-safe" in joined
    assert "gate_verdict" in joined


def test_validate_passes_for_default_gate(db_session) -> None:
    rule = build_default_vlm_gate(db_session, name="Good Gate")
    db_session.commit()
    resp = _client(db_session, _admin()).post(f"/api/v1/gate-graphs/{rule.id}/validate")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


# -- test-run ----------------------------------------------------------------


def test_test_run_returns_verdict(db_session) -> None:
    rule = build_default_vlm_gate(db_session, name="Run Gate")
    db_session.commit()
    fake = _FakeGuidedService()
    resp = _client(db_session, _admin(), guided_service=fake).post(
        f"/api/v1/gate-graphs/{rule.id}/test-run",
        json={"person_id": "p1", "camera_ids": ["cam1"], "profile": "confirm"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["complete"] is True
    assert body["confidence"] == 0.82
    assert body["cost"]["model_calls"] == 1
    assert fake.calls[0]["gate_rule_id"] == rule.id
    assert fake.calls[0]["camera_ids"] == ["cam1"]


def test_test_run_fails_closed_without_service(db_session) -> None:
    rule = build_default_vlm_gate(db_session, name="No Service Gate")
    db_session.commit()
    resp = _client(db_session, _admin()).post(
        f"/api/v1/gate-graphs/{rule.id}/test-run", json={}
    )
    assert resp.status_code == 200
    assert resp.json()["complete"] is False
    assert resp.json()["reason"] == "gate_service_unavailable"


# -- presets -----------------------------------------------------------------


def test_presets_endpoint_lists_seeded_presets(db_session) -> None:
    resp = _client(db_session, _admin()).get("/api/v1/gate-presets")
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()}
    assert {"generic_vlm_confirm", "kettle_on_hob", "person_at_sink"} <= keys


# -- auth --------------------------------------------------------------------


def test_auth_required_and_rejected_without_permission(db_session) -> None:
    # No credentials at all -> 401.
    assert _client(db_session).get("/api/v1/gate-graphs").status_code == 401
    assert _client(db_session).get("/api/v1/gate-presets").status_code == 401
    assert (
        _client(db_session).post("/api/v1/gate-graphs", json={"name": "x"}).status_code == 401
    )

    # Read-only key cannot write.
    reader = _reader()
    assert (
        _client(db_session, reader).post("/api/v1/gate-graphs", json={"name": "x"}).status_code
        == 403
    )
    # Read-only key can read.
    assert _client(db_session, reader).get("/api/v1/gate-graphs").status_code == 200


def test_auth_yaml_covers_gate_graph_routes() -> None:
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    pm = data["permission_map"]
    assert "GET /api/v1/gate-graphs" in pm["gate_graphs:read"]
    assert "GET /api/v1/gate-presets" in pm["gate_graphs:read"]
    assert "POST /api/v1/gate-graphs" in pm["gate_graphs:write"]
    assert "POST /api/v1/gate-graphs/*" in pm["gate_graphs:write"]
    assert "gate_graphs:read" in pm["caregiver"]
    assert "gate_graphs:write" in pm["caregiver"]
