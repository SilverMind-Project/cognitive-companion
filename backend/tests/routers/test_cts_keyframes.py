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
from backend.routers.dependencies import (
    get_keyframe_read_service,
    get_orchestrator_client,
)
from backend.schemas.cts_keyframe import (
    IdentitySummaryItem,
    KeyframePage,
    PhysicalFrameCard,
)

_SAMPLE_KEYFRAME = {
    "sample_id": "01HXYZ",
    "camera_id": "kitchen-cam",
    "captured_at": "2026-04-23T10:00:00+00:00",
    "tag_reason": "periodic",
    "quality": 0.85,
}


def _sample_page() -> KeyframePage:
    card = PhysicalFrameCard(
        physical_frame_id="pf-1",
        camera_id="kitchen-cam",
        minio_key="frames/kitchen-cam/0001-0.jpg",
        captured_at="2026-04-23T10:00:00+00:00",
        frame_width=1920,
        frame_height=1080,
        triggers=[],
        trigger_reasons=["periodic"],
        identity_summary=[
            IdentitySummaryItem(
                effective_identity_id="grandma",
                person_id="grandma",
                count=1,
                source_badges=["ArcFace"],
            )
        ],
        unknown_count=0,
        conflict_count=0,
        pending_review_count=0,
        bboxes=[],
        keyframe_id="pf-1",
        sample_id="pf-1",
    )
    return KeyframePage(keyframes=[card], count=1, total=1, limit=50, offset=0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_app(cts_enabled: bool = True, orchestrator: OrchestratorClient | None = None):
    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    if orchestrator is None:
        orchestrator = MagicMock(spec=OrchestratorClient)
        orchestrator.get_keyframe = AsyncMock(return_value=_SAMPLE_KEYFRAME)
        orchestrator.retain_keyframe = AsyncMock(return_value={"retained": True})

    read_service = MagicMock()
    read_service.list_frames = AsyncMock(return_value=_sample_page())

    app = FastAPI()
    app.state.minio_client = None
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.dependency_overrides[get_orchestrator_client] = lambda: orchestrator
    app.dependency_overrides[get_keyframe_read_service] = lambda: read_service

    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    return TestClient(app), orchestrator, read_service, patcher


@pytest.fixture
def client_and_orch():
    c, o, _s, p = _build_app(cts_enabled=True)
    yield c, o
    p.stop()


@pytest.fixture
def client_and_service():
    c, _o, s, p = _build_app(cts_enabled=True)
    yield c, s
    p.stop()


@pytest.fixture
def client_off():
    c, _o, _s, p = _build_app(cts_enabled=False)
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
    def test_returns_grouped_cards(self, client_and_service):
        client, _ = client_and_service
        r = client.get("/api/v1/cts/keyframes")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        assert body["total"] == 1
        card = body["keyframes"][0]
        assert card["physical_frame_id"] == "pf-1"
        assert card["identity_summary"][0]["effective_identity_id"] == "grandma"

    def test_passes_filters_to_service(self, client_and_service):
        client, svc = client_and_service
        client.get(
            "/api/v1/cts/keyframes",
            params={"person_id": "grandma", "limit": 10, "conflict_only": "true"},
        )
        svc.list_frames.assert_awaited_once()
        kwargs = svc.list_frames.await_args.kwargs
        assert kwargs["effective_identity_id"] == "grandma"
        assert kwargs["limit"] == 10
        assert kwargs["conflict_only"] is True

    def test_invalid_limit_rejected(self, client_and_service):
        client, _ = client_and_service
        r = client.get("/api/v1/cts/keyframes", params={"limit": 0})
        assert r.status_code == 422

    def test_upstream_contract_violation_returns_502(self, client_and_service):
        from backend.services.cts.keyframe_read_service import KeyframeReadContractError

        client, svc = client_and_service
        svc.list_frames = AsyncMock(side_effect=KeyframeReadContractError("bad"))
        r = client.get("/api/v1/cts/keyframes")
        assert r.status_code == 502
        assert r.json()["detail"]["code"] == "keyframe.upstream_contract"


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
