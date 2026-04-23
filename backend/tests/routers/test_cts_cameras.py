"""Tests for the CTS cameras router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 — registers all models
from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import Base, get_db
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_cameras import router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(cts_enabled: bool = True) -> TestClient:
    from unittest.mock import patch

    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )

    # Provide empty CTS gateway clients so the router can call _get_ingress().
    app.state.ingress_admin_client = None
    app.state.orchestrator_client = None

    patcher = patch("backend.routers.cts_cameras.settings", cfg)
    patcher.start()
    client = TestClient(app)
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


@pytest.fixture
def client():
    c = _make_client(cts_enabled=True)
    yield c
    c._patcher.stop()  # type: ignore[attr-defined]


@pytest.fixture
def client_off():
    c = _make_client(cts_enabled=False)
    yield c
    c._patcher.stop()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


CAMERA = {
    "id": "kitchen-cam-1",
    "name": "Kitchen",
    "rtsp_url": "rtsp://192.168.1.10/stream",
    "location": "Kitchen",
    "enabled": True,
}


class TestListCameras:
    def test_empty_list(self, client: TestClient):
        r = client.get("/api/v1/cts/cameras")
        assert r.status_code == 200
        assert r.json() == []

    def test_disabled_returns_404(self, client_off: TestClient):
        r = client_off.get("/api/v1/cts/cameras")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "cts.disabled"


class TestCreateCamera:
    def test_creates_camera(self, client: TestClient):
        r = client.post("/api/v1/cts/cameras", json=CAMERA)
        assert r.status_code == 201
        body = r.json()
        assert body["id"] == "kitchen-cam-1"
        assert body["has_homography"] is False
        assert body["privacy_zone_count"] == 0

    def test_duplicate_returns_409(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.post("/api/v1/cts/cameras", json=CAMERA)
        assert r.status_code == 409

    def test_list_returns_created_camera(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.get("/api/v1/cts/cameras")
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert "kitchen-cam-1" in ids


class TestGetCamera:
    def test_get_existing(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.get("/api/v1/cts/cameras/kitchen-cam-1")
        assert r.status_code == 200
        assert r.json()["name"] == "Kitchen"

    def test_get_missing_returns_404(self, client: TestClient):
        r = client.get("/api/v1/cts/cameras/nonexistent")
        assert r.status_code == 404


class TestUpdateCamera:
    def test_patch_name(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.patch("/api/v1/cts/cameras/kitchen-cam-1", json={"name": "Kitchen 2"})
        assert r.status_code == 200
        assert r.json()["name"] == "Kitchen 2"

    def test_patch_missing_returns_404(self, client: TestClient):
        r = client.patch("/api/v1/cts/cameras/nonexistent", json={"name": "X"})
        assert r.status_code == 404

    def test_patch_enabled_toggle(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.patch("/api/v1/cts/cameras/kitchen-cam-1", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["enabled"] is False


class TestDeleteCamera:
    def test_delete_existing(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.delete("/api/v1/cts/cameras/kitchen-cam-1")
        assert r.status_code == 204
        r2 = client.get("/api/v1/cts/cameras/kitchen-cam-1")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client: TestClient):
        r = client.delete("/api/v1/cts/cameras/nonexistent")
        assert r.status_code == 404


class TestTestConnect:
    def test_missing_rtsp_url_returns_422(self, client: TestClient):
        r = client.post("/api/v1/cts/cameras/test-connect", json={})
        assert r.status_code == 422
