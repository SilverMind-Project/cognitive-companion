"""MCP/BFF parity test for get_gait_trend: D6 guarantee.

Both the MCP tool and the BFF router must call the same GaitTrendService
and return the same envelope shape for the same input.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.mcp.server import _svc
from backend.mcp.server import get_gait_trend as mcp_get_gait_trend
from backend.routers.cts_gait import _get_service
from backend.routers.cts_gait import router as gait_router
from backend.schemas.gait import GaitDayPoint, GaitTrendEnvelope


def _build_envelope(person_id: str = "alice") -> GaitTrendEnvelope:
    today = datetime.now(UTC).date()
    return GaitTrendEnvelope(
        person_id=person_id,
        days=[
            GaitDayPoint(
                date=(today - timedelta(days=i)).isoformat(),
                median_speed_m_s=0.85,
                bout_count=5,
                total_walking_s=150.0,
                sufficient=True,
            )
            for i in range(1, 30)
        ],
        baseline_median_m_s=0.90,
        trend="stable",
    )


@pytest.fixture(autouse=True)
def reset_svc():
    original = _svc.__dict__.copy()
    yield
    for k, v in original.items():
        setattr(_svc, k, v)


@pytest.mark.asyncio
async def test_mcp_bff_same_person_id():
    """MCP and BFF return the same person_id for the same request."""
    env = _build_envelope("alice")
    svc_mock = AsyncMock()
    svc_mock.get_gait_trend = AsyncMock(return_value=env)

    _svc.gait_trend_service = svc_mock
    mcp_result = await mcp_get_gait_trend(person_id="alice", days=56)

    svc_mock.get_gait_trend.reset_mock(return_value=True)
    svc_mock.get_gait_trend = AsyncMock(return_value=env)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(gait_router)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[_get_service] = lambda: svc_mock

    client = TestClient(app)
    resp = client.get("/cts/gait/trend", params={"person_id": "alice", "days": 56})
    assert resp.status_code == 200, resp.text
    bff_result = resp.json()

    assert mcp_result["person_id"] == bff_result["person_id"] == "alice"


@pytest.mark.asyncio
async def test_mcp_bff_same_trend_classification():
    """MCP and BFF return the same trend classification."""
    env = _build_envelope("alice")
    svc_mock = AsyncMock()
    svc_mock.get_gait_trend = AsyncMock(return_value=env)

    _svc.gait_trend_service = svc_mock
    mcp_result = await mcp_get_gait_trend(person_id="alice", days=56)

    svc_mock.get_gait_trend.reset_mock(return_value=True)
    svc_mock.get_gait_trend = AsyncMock(return_value=env)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(gait_router)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[_get_service] = lambda: svc_mock

    client = TestClient(app)
    resp = client.get("/cts/gait/trend", params={"person_id": "alice", "days": 56})
    bff_result = resp.json()

    assert mcp_result["trend"] == bff_result["trend"]


@pytest.mark.asyncio
async def test_mcp_returns_error_when_service_unavailable():
    """MCP returns an error dict when gait_trend_service is None."""
    _svc.gait_trend_service = None
    result = await mcp_get_gait_trend(person_id="alice")
    assert "error" in result
