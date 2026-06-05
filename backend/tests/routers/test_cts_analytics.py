"""Router tests for the CTS analytics heatmap endpoint.

Cover the time-of-day filter contract: minutes-of-day pass through to the
service, the window may wrap past midnight, and both bounds must be supplied
together (or neither).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_analytics import router as analytics_router
from backend.routers.dependencies import get_person_location_service
from backend.schemas.cts_analytics import HeatmapEnvelope

_START = "2026-05-01T00:00:00Z"
_END = "2026-05-08T00:00:00Z"
_PARAMS = {"person_id": "alice", "start_time": _START, "end_time": _END}


def _make_client(svc_mock: AsyncMock) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(analytics_router)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[get_person_location_service] = lambda: svc_mock
    return TestClient(app)


def _svc_mock() -> AsyncMock:
    svc = AsyncMock()
    svc.get_heatmap = AsyncMock(
        return_value=HeatmapEnvelope(person_id="alice", bins=[])
    )
    return svc


def test_heatmap_no_time_filter_passes_none_minutes() -> None:
    svc = _svc_mock()
    client = _make_client(svc)

    resp = client.get("/api/v1/cts/analytics/heatmap", params=_PARAMS)

    assert resp.status_code == 200
    _, kwargs = svc.get_heatmap.call_args
    assert kwargs["filter_start_minute"] is None
    assert kwargs["filter_end_minute"] is None


def test_heatmap_cross_midnight_window_passes_minutes() -> None:
    svc = _svc_mock()
    client = _make_client(svc)

    # Night window 21:00-06:00 wraps past midnight.
    resp = client.get(
        "/api/v1/cts/analytics/heatmap",
        params={**_PARAMS, "start_minute": 1260, "end_minute": 360},
    )

    assert resp.status_code == 200
    _, kwargs = svc.get_heatmap.call_args
    assert kwargs["filter_start_minute"] == 1260
    assert kwargs["filter_end_minute"] == 360


def test_heatmap_half_specified_time_filter_is_rejected() -> None:
    svc = _svc_mock()
    client = _make_client(svc)

    resp = client.get(
        "/api/v1/cts/analytics/heatmap",
        params={**_PARAMS, "start_minute": 1260},
    )

    assert resp.status_code == 422
    svc.get_heatmap.assert_not_called()


def test_heatmap_start_after_end_is_rejected() -> None:
    svc = _svc_mock()
    client = _make_client(svc)

    resp = client.get(
        "/api/v1/cts/analytics/heatmap",
        params={"person_id": "alice", "start_time": _END, "end_time": _START},
    )

    assert resp.status_code == 422
    svc.get_heatmap.assert_not_called()


@pytest.mark.parametrize("bad_minute", [-1, 1440])
def test_heatmap_out_of_range_minute_is_rejected(bad_minute: int) -> None:
    svc = _svc_mock()
    client = _make_client(svc)

    resp = client.get(
        "/api/v1/cts/analytics/heatmap",
        params={**_PARAMS, "start_minute": bad_minute, "end_minute": 360},
    )

    assert resp.status_code == 422
    svc.get_heatmap.assert_not_called()
