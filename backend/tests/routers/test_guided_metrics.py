from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers import guided_metrics
from backend.routers.dependencies import get_guided_metrics_service
from backend.schemas.guided_metrics import (
    GuidedCompletionSummaryEnvelope,
    GuidedMetricsWindow,
)

_WINDOW = GuidedMetricsWindow(
    person_id="resident-1",
    routine_id=1,
    since=datetime(2026, 6, 1, tzinfo=UTC),
    until=datetime(2026, 6, 18, tzinfo=UTC),
)


class _Service:
    def completion_summary(self, **kwargs):
        return GuidedCompletionSummaryEnvelope(
            window=_WINDOW,
            started=1,
            completed=1,
            completion_rate=1.0,
            outcomes=[],
        )


def _client(auth: AuthContext | None = None) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.state.guided_metrics_service = _Service()
    app.include_router(guided_metrics.router, prefix="/api/v1")
    app.dependency_overrides[get_guided_metrics_service] = lambda: app.state.guided_metrics_service
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def _caregiver() -> AuthContext:
    return AuthContext(key="caregiver", name="Caregiver", permissions=["guided_metrics:read"])


def test_completion_route_returns_envelope() -> None:
    response = _client(_caregiver()).get(
        "/api/v1/guided-metrics/completion",
        params={"person_id": "resident-1", "routine_id": 1},
    )

    assert response.status_code == 200
    assert response.json()["completion_rate"] == 1.0


def test_guided_metrics_requires_auth() -> None:
    response = _client().get(
        "/api/v1/guided-metrics/completion",
        params={"person_id": "resident-1", "routine_id": 1},
    )

    assert response.status_code == 401


def test_auth_yaml_covers_guided_metrics_routes() -> None:
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    permission_map = data["permission_map"]

    assert "GET /api/v1/guided-metrics/*" in permission_map["guided_metrics:read"]
    assert "guided_metrics:read" in permission_map["caregiver"]
