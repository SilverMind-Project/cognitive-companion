"""U2-T5: CTS dashboard router tests — 503 on orchestrator failure, no silent swallow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_dashboard import _get_orchestrator_client, router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_app(client_mock: AsyncMock, cts_on: bool = True) -> TestClient:
    """Return a TestClient with a mocked orchestrator client."""
    mock_settings = MagicMock()
    mock_settings.as_bool = MagicMock(return_value=cts_on)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[_get_orchestrator_client] = lambda: client_mock

    with patch("backend.routers.cts_deps.settings", mock_settings):
        return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# unacknowledged-count: 503 replaces silent {"count": 0} (U2 W3 / rule 15)
# ---------------------------------------------------------------------------


class TestUnacknowledgedCount:
    def test_returns_count_when_orchestrator_ok(self):
        client_mock = AsyncMock()
        client_mock.get_dashboard_signals = AsyncMock(
            return_value={
                "signals": [
                    {"id": 1, "acknowledged_at": None},
                    {"id": 2, "acknowledged_at": "2026-05-29T10:00:00Z"},
                ]
            }
        )
        tc = _build_app(client_mock)
        with patch(
            "backend.routers.cts_deps.settings", MagicMock(as_bool=MagicMock(return_value=True))
        ):
            resp = tc.get("/api/v1/cts/dashboard/unacknowledged-count")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1

    def test_returns_503_when_orchestrator_raises(self):
        """Rule 15: orchestrator unavailable must produce 503, never {"count": 0}."""
        client_mock = AsyncMock()
        client_mock.get_dashboard_signals = AsyncMock(side_effect=Exception("connection refused"))
        tc = _build_app(client_mock)
        with patch(
            "backend.routers.cts_deps.settings", MagicMock(as_bool=MagicMock(return_value=True))
        ):
            resp = tc.get("/api/v1/cts/dashboard/unacknowledged-count")
        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"]["code"] == "cts.orchestrator_unavailable"

    def test_503_body_does_not_contain_count_zero(self):
        """The response must not be {"count": 0} — that would be a silent lie."""
        client_mock = AsyncMock()
        client_mock.get_dashboard_signals = AsyncMock(side_effect=RuntimeError("timeout"))
        tc = _build_app(client_mock)
        with patch(
            "backend.routers.cts_deps.settings", MagicMock(as_bool=MagicMock(return_value=True))
        ):
            resp = tc.get("/api/v1/cts/dashboard/unacknowledged-count")
        body = resp.json()
        # Must not be the old silent-swallow shape
        assert body != {"count": 0, "signals": []}
        assert "detail" in body

    def test_503_increments_metric(self):
        """503 path increments cc_cts_orchestrator_unavailable_total."""
        from prometheus_client import CollectorRegistry

        reg = CollectorRegistry()
        from backend.observability.metrics import build_location_metrics

        metrics = build_location_metrics(registry=reg)

        client_mock = AsyncMock()
        client_mock.get_dashboard_signals = AsyncMock(side_effect=Exception("down"))

        with (
            patch("backend.routers.cts_dashboard.location_metrics", metrics),
            patch(
                "backend.routers.cts_deps.settings",
                MagicMock(as_bool=MagicMock(return_value=True)),
            ),
        ):
            tc = _build_app(client_mock)
            tc.get("/api/v1/cts/dashboard/unacknowledged-count")

        value = metrics.cts_orchestrator_unavailable_total.labels(
            endpoint="unacknowledged_count"
        )._value.get()
        assert value == 1.0
