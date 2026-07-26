"""Router tests for GET /api/v1/admin/inference-telemetry (DL-M09)."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers.admin_metrics import router
from backend.routers.dependencies import get_inference_telemetry
from backend.schemas.inference_telemetry import (
    CallerLaneOutcomeOut,
    HourlyCallBucketOut,
    InferenceTelemetryOut,
    QueueDepthOut,
)

_TELEMETRY = InferenceTelemetryOut(
    window_minutes=60,
    totals_by_caller_lane=[
        CallerLaneOutcomeOut(caller="rule:tea_intent", lane="vision", ok=3, timeout=1, error=0),
    ],
    queue_depth=[
        QueueDepthOut(lane="vision", depth=0),
        QueueDepthOut(lane="text", depth=1),
    ],
    queue_wait_p50_ms=12.0,
    queue_wait_p95_ms=45.0,
    timeouts_total=1,
    calls_per_hour=[
        HourlyCallBucketOut(hour="2026-07-26T14:00:00+00:00", lane="vision", calls=4),
    ],
    ring_buffer_size=4,
    ring_buffer_capacity=2000,
)


def _build_app(*, service=None, permissions: list[str] = ("*",)):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)

    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=list(permissions)
    )
    if service is not None:
        app.dependency_overrides[get_inference_telemetry] = lambda: service
    else:
        # Leave the real dependency in place; app.state.inference_telemetry is
        # unset (None) so the 503 "service unavailable" path is exercised.
        app.state.inference_telemetry = None

    return TestClient(app, raise_server_exceptions=False)


class TestInferenceTelemetryEndpoint:
    def test_200_with_service_wired(self):
        svc = MagicMock()
        svc.get_telemetry = MagicMock(return_value=_TELEMETRY)
        client = _build_app(service=svc)

        resp = client.get("/api/v1/admin/inference-telemetry")

        assert resp.status_code == 200
        body = resp.json()
        assert body["window_minutes"] == 60
        assert body["totals_by_caller_lane"][0]["caller"] == "rule:tea_intent"
        assert body["totals_by_caller_lane"][0]["timeout"] == 1
        assert body["queue_depth"][1]["lane"] == "text"
        assert body["queue_wait_p95_ms"] == 45.0
        assert body["timeouts_total"] == 1
        assert body["calls_per_hour"][0]["calls"] == 4
        assert body["ring_buffer_capacity"] == 2000

    def test_403_without_permission(self):
        svc = MagicMock()
        svc.get_telemetry = MagicMock(return_value=_TELEMETRY)
        client = _build_app(service=svc, permissions=[])

        resp = client.get("/api/v1/admin/inference-telemetry")

        assert resp.status_code == 403

    def test_503_when_service_unavailable(self):
        client = _build_app(service=None)

        resp = client.get("/api/v1/admin/inference-telemetry")

        assert resp.status_code == 503
