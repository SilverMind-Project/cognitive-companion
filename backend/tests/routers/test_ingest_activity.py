"""U5-T5: GET /pipeline/ingest/activity endpoint.

Verifies:
- Returns an explicit empty list when no ingest exists (rule 15)
- Returns recorded frame_received events from MediaCache
- Returns recorded rule_triggered events from EventLog
- The endpoint uses the real PipelineRunService with a real DB (integration path)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.models.event import EventLog
from backend.models.media_cache import MediaCache
from backend.routers.pipeline_runs import router
from backend.services.pipeline_run_service import PipelineRunService

# ---------------------------------------------------------------------------
# App factory using real PipelineRunService + real DB
# ---------------------------------------------------------------------------


def _build_app(db_factory) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="admin", permissions=["*"]
    )
    app.state.pipeline_run_service = PipelineRunService(db_factory=db_factory)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIngestActivityWithRealDB:
    def test_empty_db_returns_empty_list(self, db_factory):
        """Rule 15: no ingest → explicit empty list, not an error."""
        tc = _build_app(db_factory)
        resp = tc.get("/api/v1/pipeline/ingest/activity")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_frame_received_from_media_cache(self, db_factory):
        db = db_factory()
        now = datetime.now(UTC)
        mc = MediaCache(
            object_name="pipeline/test/frame1.jpg",
            sensor_id="recamera_kitchen1",
            captured_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(mc)
        db.commit()
        db.close()

        tc = _build_app(db_factory)
        resp = tc.get("/api/v1/pipeline/ingest/activity")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) >= 1
        frame_events = [e for e in body if e["event_type"] == "frame_received"]
        assert len(frame_events) >= 1
        assert frame_events[0]["sensor_id"] == "recamera_kitchen1"

    def test_returns_rule_triggered_from_event_log(self, db_factory):
        db = db_factory()
        now = datetime.now(UTC)
        el = EventLog(
            rule_name="motion-alert",
            sensor_id="recamera_livingroom",
            trigger_type="sensor_event",
            status="completed",
            timestamp=now,
        )
        db.add(el)
        db.commit()
        db.close()

        tc = _build_app(db_factory)
        resp = tc.get("/api/v1/pipeline/ingest/activity")

        assert resp.status_code == 200
        body = resp.json()
        rule_events = [e for e in body if e["event_type"] == "rule_triggered"]
        assert len(rule_events) >= 1
        assert rule_events[0]["rule_name"] == "motion-alert"
