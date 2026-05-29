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
