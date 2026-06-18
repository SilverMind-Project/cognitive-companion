from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.mcp.server import _svc
from backend.mcp.server import get_guided_completion_summary as mcp_completion_summary
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
            started=2,
            completed=1,
            completion_rate=0.5,
            outcomes=[],
        )


@pytest.mark.asyncio
async def test_completion_summary_mcp_bff_parity() -> None:
    original = _svc.guided_metrics_service
    service = _Service()
    _svc.guided_metrics_service = service
    try:
        mcp_result = await mcp_completion_summary(person_id="resident-1", routine_id=1)

        app = FastAPI()
        register_exception_handlers(app)
        app.state.guided_metrics_service = service
        app.include_router(guided_metrics.router, prefix="/api/v1")
        app.dependency_overrides[get_guided_metrics_service] = lambda: service
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            key="x", name="tester", permissions=["*"]
        )
        response = TestClient(app).get(
            "/api/v1/guided-metrics/completion",
            params={"person_id": "resident-1", "routine_id": 1},
        )
    finally:
        _svc.guided_metrics_service = original

    assert response.status_code == 200
    assert mcp_result["completion_rate"] == response.json()["completion_rate"]
    assert mcp_result["window"]["person_id"] == response.json()["window"]["person_id"]
