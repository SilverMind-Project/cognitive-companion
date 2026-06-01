"""Integration tests for the CTS keyframes router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.integrations.tracking_orchestrator_client import OrchestratorClient
from backend.routers.cts_keyframes import router
from backend.routers.dependencies import get_orchestrator_client

_SAMPLE_KEYFRAME = {
    "sample_id": "01HXYZ",
    "camera_id": "kitchen-cam",
    "captured_at": "2026-04-23T10:00:00+00:00",
    "tag_reason": "periodic",
    "quality": 0.85,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_app(cts_enabled: bool = True, orchestrator: OrchestratorClient | None = None):
    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    if orchestrator is None:
        orchestrator = MagicMock(spec=OrchestratorClient)
        orchestrator.list_keyframes = AsyncMock(return_value=[_SAMPLE_KEYFRAME])
        orchestrator.get_keyframe = AsyncMock(return_value=_SAMPLE_KEYFRAME)
        orchestrator.retain_keyframe = AsyncMock(return_value={"retained": True})

    app = FastAPI()
    app.state.minio_client = None
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[get_orchestrator_client] = lambda: orchestrator

    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    return TestClient(app), orchestrator, patcher


@pytest.fixture
def client_and_orch():
    c, o, p = _build_app(cts_enabled=True)
    yield c, o
    p.stop()


@pytest.fixture
def client_off():
    c, _, p = _build_app(cts_enabled=False)
    yield c
    p.stop()


# ---------------------------------------------------------------------------
# CTS disabled guard
# ---------------------------------------------------------------------------


class TestCTSDisabledGuard:
    def test_list_disabled(self, client_off: TestClient):
        r = client_off.get("/api/v1/cts/keyframes")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "cts.disabled"

    def test_get_disabled(self, client_off: TestClient):
        r = client_off.get("/api/v1/cts/keyframes/01HXYZ")
        assert r.status_code == 404

    def test_retain_disabled(self, client_off: TestClient):
        r = client_off.post("/api/v1/cts/keyframes/01HXYZ/retain")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /cts/keyframes
# ---------------------------------------------------------------------------


class TestListKeyframes:
    def test_returns_keyframes(self, client_and_orch):
        client, _ = client_and_orch
        r = client.get("/api/v1/cts/keyframes")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["keyframes"][0]["sample_id"] == "01HXYZ"

    def test_passes_filters_to_orchestrator(self, client_and_orch):
        client, orch = client_and_orch
        client.get("/api/v1/cts/keyframes", params={"person_id": "grandma", "limit": 10})
        orch.list_keyframes.assert_awaited_once_with(
            person_id="grandma",
            signal_type=None,
            after=None,
            limit=10,
        )

    def test_invalid_limit_rejected(self, client_and_orch):
        client, _ = client_and_orch
        r = client.get("/api/v1/cts/keyframes", params={"limit": 0})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /cts/keyframes/{sample_id}
# ---------------------------------------------------------------------------


class TestGetKeyframe:
    def test_returns_keyframe(self, client_and_orch):
        client, _ = client_and_orch
        r = client.get("/api/v1/cts/keyframes/01HXYZ")
        assert r.status_code == 200
        assert r.json()["sample_id"] == "01HXYZ"

    def test_not_found_returns_404(self, client_and_orch):
        client, orch = client_and_orch
        from backend.integrations._upstream_base import UpstreamError

        orch.get_keyframe = AsyncMock(side_effect=UpstreamError("orchestrator", 404))
        r = client.get("/api/v1/cts/keyframes/missing")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "keyframe.not_found"


# ---------------------------------------------------------------------------
# POST /cts/keyframes/{sample_id}/retain
# ---------------------------------------------------------------------------


class TestRetainKeyframe:
    def test_retain_returns_success(self, client_and_orch):
        client, _ = client_and_orch
        r = client.post("/api/v1/cts/keyframes/01HXYZ/retain")
        assert r.status_code == 200
        body = r.json()
        assert body["retained"] is True
        assert body["sample_id"] == "01HXYZ"

    def test_not_found_returns_404(self, client_and_orch):
        client, orch = client_and_orch
        from backend.integrations._upstream_base import UpstreamError

        orch.retain_keyframe = AsyncMock(side_effect=UpstreamError("orchestrator", 404))
        r = client.post("/api/v1/cts/keyframes/missing/retain")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "keyframe.not_found"
