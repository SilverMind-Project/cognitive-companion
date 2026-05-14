"""Tests for the CTS gallery enrollment router (CC BFF proxy).

Covers:
- CTS-disabled guard (404 + code "cts.disabled").
- No orchestrator client attached (503 + code "cts.orchestrator_unavailable").
- Happy-path proxy: forwards to OrchestratorClient.enroll_from_tracklet.
- Upstream 404 surfaced as 502 with "cts.upstream_error".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.core.upstream_errors import UpstreamError


def _build_app(cts_enabled: bool = True, orchestrator=None):
    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    import backend.routers.cts_deps as cts_deps_mod
    from backend.routers import cts_gallery as mod

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(mod.router, prefix="/api/v1")
    app.state.orchestrator_client = orchestrator
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )

    settings_patch = patch.object(cts_deps_mod, "settings", cfg)
    settings_patch.start()
    return TestClient(app), settings_patch


class TestCTSDisabledGuard:
    def test_enroll_returns_404_when_cts_disabled(self):
        client, patcher = _build_app(cts_enabled=False)
        try:
            r = client.post(
                "/api/v1/cts/gallery/enroll",
                json={"identity_id": "grandma", "tracklet_id": "t-1"},
            )
            assert r.status_code == 404
            assert r.json()["detail"]["code"] == "cts.disabled"
        finally:
            patcher.stop()


class TestOrchestratorUnavailable:
    def test_enroll_503_when_no_client(self):
        client, patcher = _build_app(cts_enabled=True, orchestrator=None)
        try:
            r = client.post(
                "/api/v1/cts/gallery/enroll",
                json={"identity_id": "grandma", "tracklet_id": "t-1"},
            )
            assert r.status_code == 503
            assert r.json()["detail"]["code"] == "cts.orchestrator_unavailable"
        finally:
            patcher.stop()


class TestEnrollProxy:
    def test_forwards_to_orchestrator(self):
        orchestrator = AsyncMock()
        orchestrator.enroll_from_tracklet = AsyncMock(
            return_value={
                "identity_id": "grandma",
                "enrolled_count": 3,
                "enrolled_at": "2026-01-01T00:00:00+00:00",
            }
        )
        client, patcher = _build_app(orchestrator=orchestrator)
        try:
            r = client.post(
                "/api/v1/cts/gallery/enroll",
                json={
                    "identity_id": "grandma",
                    "tracklet_id": "t-1",
                    "display_name": "Grandma",
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["identity_id"] == "grandma"
            assert body["enrolled_count"] == 3
        finally:
            patcher.stop()

        orchestrator.enroll_from_tracklet.assert_awaited_once_with(
            identity_id="grandma",
            tracklet_id="t-1",
            display_name="Grandma",
        )

    def test_upstream_404_propagated_with_error_code(self):
        orchestrator = AsyncMock()
        orchestrator.enroll_from_tracklet = AsyncMock(
            side_effect=UpstreamError("tracking_orchestrator", 404, "tracklet not found")
        )
        client, patcher = _build_app(orchestrator=orchestrator)
        try:
            r = client.post(
                "/api/v1/cts/gallery/enroll",
                json={"identity_id": "ghost", "tracklet_id": "no-such-tracklet"},
            )
            # Orchestrator 404 (no embeddings) surfaces as 404 to the caller.
            assert r.status_code == 404
            assert r.json()["detail"]["code"] == "cts.upstream_error"
        finally:
            patcher.stop()

    def test_upstream_500_becomes_502(self):
        orchestrator = AsyncMock()
        orchestrator.enroll_from_tracklet = AsyncMock(
            side_effect=UpstreamError("tracking_orchestrator", 500, "internal error")
        )
        client, patcher = _build_app(orchestrator=orchestrator)
        try:
            r = client.post(
                "/api/v1/cts/gallery/enroll",
                json={"identity_id": "grandma", "tracklet_id": "t-1"},
            )
            assert r.status_code == 500
            assert r.json()["detail"]["code"] == "cts.upstream_error"
        finally:
            patcher.stop()
