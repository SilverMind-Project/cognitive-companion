"""Parity tests for rule bundle import through router and MCP."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule, RuleContext
from backend.routers import rules as rules_module
from backend.routers.rules import router
from backend.steps import StepRegistry

StepRegistry.discover()


@pytest.fixture
def client(db_factory, monkeypatch):
    app = FastAPI()
    register_exception_handlers(app)
    monkeypatch.setattr(rules_module, "_app_version", lambda: "1.0.0")

    async def override_get_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    async def override_auth():
        return AuthContext(
            key="test",
            name="Test Admin",
            permissions=["*"],
            device_type=None,
            sensor_id=None,
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_auth_context] = override_auth
    app.include_router(router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def _bundle_dict(name: str) -> dict[str, Any]:
    return {
        "rule": {
            "name": name,
            "enabled": True,
            "trigger_types": ["manual"],
        },
        "contexts": [
            {
                "context_type": "time_range",
                "config": {"start_time": "08:00", "end_time": "20:00"},
                "negate": False,
            }
        ],
        "steps": [
            {
                "label": "check",
                "step_type": "condition",
                "position_x": 10.0,
                "position_y": 20.0,
                "config": {"expression": "true"},
            },
            {
                "label": "notify",
                "step_type": "notification",
                "position_x": 30.0,
                "position_y": 40.0,
                "config": {},
            },
            {
                "label": "wait",
                "step_type": "wait",
                "position_x": 30.0,
                "position_y": 80.0,
                "config": {},
            },
        ],
        "edges": [
            {
                "source_label": "check",
                "source_port": "true",
                "target_label": "notify",
                "target_port": "main",
            },
            {
                "source_label": "check",
                "source_port": "false",
                "target_label": "wait",
                "target_port": "main",
            },
        ],
    }


def _snapshot_rule(db_factory, name: str) -> dict[str, Any]:
    db = db_factory()
    try:
        rule = db.query(Rule).filter(Rule.name == name).one()
        steps = (
            db.query(PipelineStep)
            .filter(PipelineStep.rule_id == rule.id)
            .order_by(PipelineStep.order)
            .all()
        )
        labels_by_id = {step.id: step.label for step in steps}
        edges = (
            db.query(PipelineEdge)
            .filter(PipelineEdge.rule_id == rule.id)
            .order_by(PipelineEdge.source_port)
            .all()
        )
        return {
            "step_labels": [step.label for step in steps],
            "positions": [(step.label, step.position_x, step.position_y) for step in steps],
            "edges": [
                (
                    labels_by_id[edge.source_step_id],
                    edge.source_port,
                    labels_by_id[edge.target_step_id],
                    edge.target_port,
                )
                for edge in edges
            ],
            "context_count": db.query(RuleContext).filter(RuleContext.rule_id == rule.id).count(),
        }
    finally:
        db.close()


@pytest.mark.asyncio
async def test_router_and_mcp_import_produce_identical_rule(
    client,
    db_factory,
    monkeypatch,
):
    from backend.mcp import server as mcp_server
    from backend.mcp.server import import_rule_bundle

    monkeypatch.setattr("importlib.metadata.version", lambda _package: "1.0.0")
    old_db_factory = mcp_server._svc.db_factory
    mcp_server._svc.db_factory = db_factory

    router_bundle = _bundle_dict("parity-router")
    mcp_bundle = deepcopy(router_bundle)
    mcp_bundle["rule"]["name"] = "parity-mcp"

    try:
        router_response = client.post("/api/v1/rules/import", json=router_bundle)
        mcp_response = await import_rule_bundle(mcp_bundle, mode="commit")
    finally:
        mcp_server._svc.db_factory = old_db_factory

    assert router_response.status_code == 201
    assert router_response.json()["status"] == "ok"
    assert mcp_response["status"] == "ok"
    assert _snapshot_rule(db_factory, "parity-router") == _snapshot_rule(
        db_factory,
        "parity-mcp",
    )
