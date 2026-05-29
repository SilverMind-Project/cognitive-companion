"""U5-T2: Pipeline runs router tests.

Verifies:
- GET /pipeline/runs returns the envelope list
- GET /pipeline/runs/{id} returns the envelope for a known execution
- GET /pipeline/runs/{id} returns 404 for a missing execution (not a fabricated envelope)
- Unauthorised request is rejected
- GET /pipeline/ingest/activity returns a list (empty or otherwise)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.routers.pipeline_runs import router
from backend.schemas.pipeline_run import IngestActivityEnvelope, PipelineRunEnvelope

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_envelope(execution_id: int = 1) -> PipelineRunEnvelope:
    from datetime import UTC, datetime

    return PipelineRunEnvelope(
        execution_id=execution_id,
        rule_id=1,
        rule_name="test-rule",
        status="running",
        started_at=datetime.now(UTC),
        nodes=[],
        edges=[],
    )


def _build_app(svc: MagicMock, authed: bool = True) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    if authed:
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            key="x", name="admin", permissions=["*"]
        )
    app.state.pipeline_run_service = svc
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /pipeline/runs
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_returns_envelope_list(self):
        svc = MagicMock()
        svc.recent_runs.return_value = [_make_envelope(1), _make_envelope(2)]
        tc = _build_app(svc)

        resp = tc.get("/api/v1/pipeline/runs")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["execution_id"] == 1

    def test_active_filter_calls_list_active_runs(self):
        svc = MagicMock()
        svc.list_active_runs.return_value = [_make_envelope(3)]
        tc = _build_app(svc)

        resp = tc.get("/api/v1/pipeline/runs?status=active")

        assert resp.status_code == 200
        svc.list_active_runs.assert_called_once()

    def test_unauthorised_rejected(self):
        svc = MagicMock()
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")
        app.state.pipeline_run_service = svc
        tc = TestClient(app, raise_server_exceptions=False)

        resp = tc.get("/api/v1/pipeline/runs")

        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /pipeline/runs/{id}
# ---------------------------------------------------------------------------


class TestGetRun:
    def test_returns_envelope_for_known_execution(self):
        svc = MagicMock()
        svc.get_run.return_value = _make_envelope(42)
        tc = _build_app(svc)

        resp = tc.get("/api/v1/pipeline/runs/42")

        assert resp.status_code == 200
        assert resp.json()["execution_id"] == 42

    def test_404_for_missing_execution(self):
        """Rule 15: missing execution must return 404, not a fabricated envelope."""
        svc = MagicMock()
        svc.get_run.return_value = None
        tc = _build_app(svc)

        resp = tc.get("/api/v1/pipeline/runs/99999")

        assert resp.status_code == 404
        assert "99999" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# GET /pipeline/ingest/activity
# ---------------------------------------------------------------------------


class TestIngestActivity:
    def test_returns_list_when_no_ingest(self):
        """Rule 15: empty ingest → empty list, never an error."""
        svc = MagicMock()
        svc.list_ingest_activity.return_value = []
        tc = _build_app(svc)

        resp = tc.get("/api/v1/pipeline/ingest/activity")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_ingest_events(self):
        from datetime import UTC, datetime

        svc = MagicMock()
        svc.list_ingest_activity.return_value = [
            IngestActivityEnvelope(
                id="frame-1",
                event_type="frame_received",
                timestamp=datetime.now(UTC),
                sensor_id="recamera_kitchen1",
            )
        ]
        tc = _build_app(svc)

        resp = tc.get("/api/v1/pipeline/ingest/activity")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["event_type"] == "frame_received"
