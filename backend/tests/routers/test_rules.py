"""Integration tests for rules router endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.models.rule import Rule
from backend.routers.rules import router


@pytest.fixture
def mock_pipeline_executor():
    executor = AsyncMock()

    class MockExecution:
        id = 123
        status = "running"

    executor.execute.return_value = MockExecution()
    return executor


@pytest.fixture
def client(db_session, mock_pipeline_executor):
    app = FastAPI()
    register_exception_handlers(app)
    app.state.pipeline_executor = mock_pipeline_executor

    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Override auth with admin context
    async def override_auth():
        return AuthContext(
            key="test", name="Test Admin", permissions=["*"], device_type=None, sensor_id=None
        )

    app.dependency_overrides[get_auth_context] = override_auth
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestRulesRouter:
    def test_validate_rule_endpoint(self, client, db_session):
        # Create a test rule
        rule = Rule(
            name="Test Validate Rule",
            description="Testing template validation",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(f"/api/v1/rules/{rule.id}/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_id"] == rule.id
        assert data["valid"] is True
        assert data["errors"] == {}

    def test_add_step_rejects_schema_invalid_config(self, client, db_session):
        rule = Rule(
            name="Test Add Step Schema",
            description="Testing add_step schema validation",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={
                "step_type": "wait",
                "config_json": {"minutes": "not-a-number"},
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "errors" in detail
        assert any("minutes" in str(e) for e in detail["errors"])

    def test_add_step_accepts_schema_valid_config(self, client, db_session):
        rule = Rule(
            name="Test Add Step Valid",
            description="Testing add_step with a valid config",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={"step_type": "wait", "config_json": {"minutes": 5}},
        )
        assert resp.status_code == 201

    def test_add_step_empty_config_is_not_validated(self, client, db_session):
        """An empty config_json is the palette's placeholder state, not a malformed config."""
        rule = Rule(
            name="Test Add Step Empty",
            description="Testing add_step with an empty config (canvas placeholder)",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={"step_type": "quiz_start", "config_json": {}},
        )
        assert resp.status_code == 201

    def test_update_step_rejects_schema_invalid_config(self, client, db_session):
        rule = Rule(
            name="Test Update Step Schema",
            description="Testing update_step schema validation",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        create_resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={"step_type": "wait", "config_json": {"minutes": 5}},
        )
        assert create_resp.status_code == 201
        step_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/rules/{rule.id}/steps/{step_id}",
            json={"config_json": {"minutes": "not-a-number"}},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "errors" in detail

    def test_update_step_accepts_schema_valid_config(self, client, db_session):
        rule = Rule(
            name="Test Update Step Valid",
            description="Testing update_step with a valid config",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        create_resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={"step_type": "wait", "config_json": {"minutes": 5}},
        )
        assert create_resp.status_code == 201
        step_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/rules/{rule.id}/steps/{step_id}",
            json={"config_json": {"minutes": 10}},
        )
        assert resp.status_code == 200

    def test_update_step_accepts_cleared_optional_field_as_null(self, client, db_session):
        """A cleared Vuetify combobox emits null; clearing a field must not itself 422.

        StepConfigDialog.vue forwards config_json unnormalized, so a previously-set optional
        field (person_id/signal_kind here) can arrive as an explicit null on save. None of
        these fields are schema-required; null must be treated as "not provided."
        """
        rule = Rule(
            name="Test Update Step Cleared Field",
            description="Testing null-as-unset on an optional enum field",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        create_resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={
                "step_type": "presence_query",
                "config_json": {"signal_kind": "pacing", "person_id": "grandma"},
            },
        )
        assert create_resp.status_code == 201
        step_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/rules/{rule.id}/steps/{step_id}",
            json={"config_json": {"signal_kind": None, "person_id": None, "output_key": "presence"}},
        )
        assert resp.status_code == 200

    def test_add_step_unknown_step_type_unchanged(self, client, db_session):
        """Unknown step types are not schema-checked (rejected elsewhere, unchanged by C7)."""
        rule = Rule(
            name="Test Add Step Unknown Type",
            description="Testing add_step with an unregistered step type",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={"step_type": "not_a_real_step_type", "config_json": {"anything": True}},
        )
        assert resp.status_code == 201

    def test_add_step_rejects_signal_kind_typo(self, client, db_session):
        rule = Rule(
            name="Test Add Step Signal Kind Typo",
            description="Testing presence_query signal_kind enum enforcement",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(
            f"/api/v1/rules/{rule.id}/steps",
            json={
                "step_type": "presence_query",
                "config_json": {"signal_kind": "gait_slowng"},
            },
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any("signal_kind" in str(e) for e in detail["errors"])

    def test_execute_rule_endpoint(self, client, db_session, mock_pipeline_executor):
        # Create a test rule
        rule = Rule(
            name="Test Execute Rule",
            description="Testing execute endpoint",
            enabled=True,
            trigger_types=["manual"],
            cool_off_minutes=5,
            max_daily_triggers=10,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        resp = client.post(f"/api/v1/rules/{rule.id}/execute")
        assert resp.status_code == 202
        data = resp.json()
        assert data["execution_id"] == 123
        assert data["status"] == "running"
        mock_pipeline_executor.execute.assert_called_once()
