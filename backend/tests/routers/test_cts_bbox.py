"""Tests for CTS bbox annotation endpoints (now proxied to orchestrator)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.models  # noqa: F401
from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import reset_default_database
from backend.core.exceptions import register_exception_handlers

_NOW = datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)
_NOW_ISO = _NOW.isoformat()


def _sample_bbox_response(**overrides) -> dict:
    default = {
        "id": "bb-001",
        "keyframe_id": "kf-test-001",
        "tracklet_id": "22222222-2222-2222-2222-222222222222",
        "camera_id": "cam-a",
        "x1": 10.0,
        "y1": 20.0,
        "x2": 100.0,
        "y2": 200.0,
        "detection_confidence": 0.95,
        "frame_width": 1920,
        "frame_height": 1080,
        "identity_id": "alice",
        "created_at": _NOW_ISO,
        "override_x1": None,
        "override_y1": None,
        "override_x2": None,
        "override_y2": None,
        "override_by": None,
        "override_at": None,
    }
    default.update(overrides)
    return default


def _build_app(cts_enabled: bool = True, orchestrator=None):
    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    from backend.routers import cts_deps
    from backend.routers import cts_identity as cts_identity_mod

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(cts_identity_mod.router, prefix="/api/v1")
    app.state.orchestrator_client = orchestrator
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )

    settings_patch = patch.object(cts_deps, "settings", cfg)
    settings_patch.start()
    patchers = (settings_patch,)
    return TestClient(app), patchers


@pytest.fixture(autouse=True)
def _reset_db():
    yield
    reset_default_database()


class TestBboxAnnotationEndpoints:
    def test_get_bboxes_returns_list(self):
        mock_client = AsyncMock()
        mock_client.get_keyframe_bboxes.return_value = [_sample_bbox_response()]

        client, patchers = _build_app(orchestrator=mock_client)
        try:
            resp = client.get("/api/v1/cts/identity/keyframes/kf-test-001/bboxes")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["keyframe_id"] == "kf-test-001"
            assert data[0]["camera_id"] == "cam-a"
            assert data[0]["x1"] == 10.0
            assert data[0]["frame_width"] == 1920
            assert data[0]["identity_id"] == "alice"
        finally:
            for p in patchers:
                p.stop()

    def test_get_bboxes_returns_empty_list_for_unknown_keyframe(self):
        mock_client = AsyncMock()
        mock_client.get_keyframe_bboxes.return_value = []

        client, patchers = _build_app(orchestrator=mock_client)
        try:
            resp = client.get("/api/v1/cts/identity/keyframes/nonexistent/bboxes")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            for p in patchers:
                p.stop()

    def test_override_bbox_updates_row(self):
        mock_client = AsyncMock()
        mock_client.override_bbox.return_value = _sample_bbox_response(
            x1=50.0, y1=60.0, x2=150.0, y2=250.0,
            override_x1=50.0, override_y1=60.0, override_x2=150.0, override_y2=250.0,
            override_by="tester", override_at=_NOW_ISO,
        )

        client, patchers = _build_app(orchestrator=mock_client)
        try:
            resp = client.put(
                "/api/v1/cts/identity/bboxes/bb-001/override",
                json={"x1": 50.0, "y1": 60.0, "x2": 150.0, "y2": 250.0},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["override_x1"] == 50.0
            assert data["override_y1"] == 60.0
            assert data["override_x2"] == 150.0
            assert data["override_y2"] == 250.0
            assert data["override_by"] == "tester"
            assert data["override_at"] is not None
            mock_client.override_bbox.assert_called_once_with(
                annotation_id="bb-001",
                x1=50.0, y1=60.0, x2=150.0, y2=250.0,
                override_by="tester",
            )
        finally:
            for p in patchers:
                p.stop()

    def test_override_bbox_not_found(self):
        from fastapi import HTTPException, status

        mock_client = AsyncMock()
        mock_client.override_bbox.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "bbox_annotation.not_found", "message": "Not found."},
        )

        client, patchers = _build_app(orchestrator=mock_client)
        try:
            resp = client.put(
                "/api/v1/cts/identity/bboxes/nonexistent/override",
                json={"x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0},
            )
            assert resp.status_code == 404
            assert resp.json()["detail"]["code"] == "bbox_annotation.not_found"
        finally:
            for p in patchers:
                p.stop()

    def test_bboxes_disabled_when_cts_off(self):
        mock_client = AsyncMock()
        client, patchers = _build_app(orchestrator=mock_client, cts_enabled=False)
        try:
            resp = client.get("/api/v1/cts/identity/keyframes/kf-test-001/bboxes")
            assert resp.status_code == 404
            assert resp.json()["detail"]["code"] == "cts.disabled"
        finally:
            for p in patchers:
                p.stop()
