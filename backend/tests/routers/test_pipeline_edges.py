"""Router tests for pipeline edge CRUD and DAG import fields."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.models.pipeline import PipelineEdge, PipelineStep
from backend.models.rule import Rule
from backend.routers import rules as rules_module
from backend.routers.rules import router


@pytest.fixture
def client(db_session, monkeypatch):
    app = FastAPI()
    register_exception_handlers(app)
    monkeypatch.setattr(rules_module, "_app_version", lambda: "1.0.0")

    async def override_get_db():
        yield db_session

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


def _create_rule(db_session, name: str = "edge-rule") -> Rule:
    rule = Rule(
        name=name,
        enabled=True,
        trigger_types=["manual"],
        cool_off_minutes=5,
        max_daily_triggers=3,
    )
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


def _add_step(
    db_session,
    rule_id: int,
    order: int,
    label: str,
    step_type: str = "notification",
) -> PipelineStep:
    step = PipelineStep(
        rule_id=rule_id,
        order=order,
        step_type=step_type,
        label=label,
        config_json={},
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(step)
    return step


def test_list_edges_returns_empty_for_new_rule(client, db_session):
    rule = _create_rule(db_session)

    response = client.get(f"/api/v1/rules/{rule.id}/edges")

    assert response.status_code == 200
    assert response.json() == []


def test_replace_edges_creates_edge_rows(client, db_session):
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")

    response = client.put(
        f"/api/v1/rules/{rule.id}/edges",
        json={
            "edges": [
                {
                    "source_step_id": first.id,
                    "source_port": "main",
                    "target_step_id": second.id,
                    "target_port": "main",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source_step_id"] == first.id
    assert body[0]["target_step_id"] == second.id


def test_replace_edges_allows_unwired_step_during_authoring(client, db_session):
    # An unwired third step produces two entry nodes. This is a valid
    # intermediate edit state and must be accepted (the single-entry rule is an
    # execution invariant, surfaced as a non-blocking validate-endpoint warning,
    # not an edge-save error).
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")
    _add_step(db_session, rule.id, 2, "third")

    response = client.put(
        f"/api/v1/rules/{rule.id}/edges",
        json={
            "edges": [
                {
                    "source_step_id": first.id,
                    "source_port": "main",
                    "target_step_id": second.id,
                }
            ]
        },
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_replace_edges_allows_removing_last_edge(client, db_session):
    # Regression: deleting the only edge sends an empty edge set, which leaves
    # every step as an entry node. This previously 422'd with
    # "exactly one entry node; found N", breaking edge deletion / remove-readd.
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")
    db_session.add(
        PipelineEdge(
            rule_id=rule.id,
            source_step_id=first.id,
            source_port="main",
            target_step_id=second.id,
        )
    )
    db_session.commit()

    response = client.put(f"/api/v1/rules/{rule.id}/edges", json={"edges": []})

    assert response.status_code == 200
    assert response.json() == []
    remaining = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()
    assert remaining == []


def test_replace_edges_validates_no_cycles(client, db_session):
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")

    response = client.put(
        f"/api/v1/rules/{rule.id}/edges",
        json={
            "edges": [
                {"source_step_id": first.id, "source_port": "main", "target_step_id": second.id},
                {"source_step_id": second.id, "source_port": "main", "target_step_id": first.id},
            ]
        },
    )

    assert response.status_code == 422
    assert "cycle" in response.json()["error"]


def test_replace_edges_validates_port_names(client, db_session):
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")

    response = client.put(
        f"/api/v1/rules/{rule.id}/edges",
        json={
            "edges": [
                {
                    "source_step_id": first.id,
                    "source_port": "maybe",
                    "target_step_id": second.id,
                }
            ]
        },
    )

    assert response.status_code == 422
    assert "not in declared output_ports" in response.json()["error"]


def test_replace_edges_is_atomic_on_validation_failure(client, db_session):
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")
    third = _add_step(db_session, rule.id, 2, "third")
    db_session.add_all(
        [
            PipelineEdge(
                rule_id=rule.id,
                source_step_id=first.id,
                source_port="main",
                target_step_id=second.id,
            ),
            PipelineEdge(
                rule_id=rule.id,
                source_step_id=second.id,
                source_port="main",
                target_step_id=third.id,
            ),
        ]
    )
    db_session.commit()

    # A cycle is rejected at authoring time; validation runs before the
    # delete/insert, so the existing two edges must survive unchanged.
    response = client.put(
        f"/api/v1/rules/{rule.id}/edges",
        json={
            "edges": [
                {"source_step_id": first.id, "source_port": "main", "target_step_id": second.id},
                {"source_step_id": second.id, "source_port": "main", "target_step_id": first.id},
            ]
        },
    )

    assert response.status_code == 422
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == rule.id).all()
    assert len(edges) == 2


def test_step_positions_round_trip_through_existing_step_routes(client, db_session):
    rule = _create_rule(db_session)

    created = client.post(
        f"/api/v1/rules/{rule.id}/steps",
        json={
            "step_type": "notification",
            "label": "notify",
            "config_json": {},
            "position_x": 12.5,
            "position_y": 34.5,
        },
    )
    assert created.status_code == 201
    step_id = created.json()["id"]
    assert created.json()["position_x"] == 12.5

    updated = client.put(
        f"/api/v1/rules/{rule.id}/steps/{step_id}",
        json={"position_x": 56.0, "position_y": 78.0},
    )

    assert updated.status_code == 200
    assert updated.json()["position_x"] == 56.0
    assert updated.json()["position_y"] == 78.0


def test_batch_position_update_succeeds(client, db_session):
    rule = _create_rule(db_session)
    first = _add_step(db_session, rule.id, 0, "first")
    second = _add_step(db_session, rule.id, 1, "second")

    response = client.put(
        f"/api/v1/rules/{rule.id}/steps/positions",
        json={
            "positions": [
                {"step_id": first.id, "position_x": 120.5, "position_y": 80.25},
                {"step_id": second.id, "position_x": 420.0, "position_y": 200.0},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.position_x == 120.5
    assert first.position_y == 80.25
    assert second.position_x == 420.0
    assert second.position_y == 200.0


def test_batch_position_update_rejects_unknown_step(client, db_session):
    rule = _create_rule(db_session)
    other_rule = _create_rule(db_session, name="other-rule")
    step = _add_step(db_session, other_rule.id, 0, "other")

    response = client.put(
        f"/api/v1/rules/{rule.id}/steps/positions",
        json={
            "positions": [
                {"step_id": step.id, "position_x": 12.0, "position_y": 34.0},
            ]
        },
    )

    assert response.status_code == 422
    assert f"Step {step.id} not in rule {rule.id}" in response.json()["error"]


def test_reorder_steps_route_is_removed(client, db_session):
    rule = _create_rule(db_session)

    response = client.put(
        f"/api/v1/rules/{rule.id}/steps/reorder",
        json={"steps": []},
    )

    assert response.status_code in {404, 405}


def test_import_rule_creates_edges_and_warns_for_missing_labels(client, db_session):
    bundle = {
        "rule": {
            "name": "import-with-edges",
            "enabled": True,
            "trigger_types": ["manual"],
        },
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
                "target_label": "missing",
                "target_port": "main",
            },
        ],
    }

    response = client.post("/api/v1/rules/import", json=bundle)

    assert response.status_code == 201
    body = response.json()
    assert body["rule_id"] is not None
    assert body["warnings"]
    edges = db_session.query(PipelineEdge).filter(PipelineEdge.rule_id == body["rule_id"]).all()
    assert len(edges) == 1
    assert edges[0].source_port == "true"
