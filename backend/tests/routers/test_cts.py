"""Tests for the CTS status and feature-flag routers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, KeyStore, get_auth_context
from backend.core.config import Settings
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts import router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app(cts_enabled: bool = True) -> FastAPI:
    """Build a minimal app with the CTS router and a fixed settings override."""
    from unittest.mock import patch

    cfg = Settings.from_dict(
        {
            "cts": {"enabled": cts_enabled},
            "cts_ui": {
                "calibration_enabled": True,
                "dashboard_enabled": True,
                "live_view_enabled": False,
            },
        }
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Inject an in-memory KeyStore that grants all CTS permissions to "testkey".
    store = KeyStore(
        api_keys=[{"key": "testkey", "name": "Test", "permissions": ["admin"]}],
        permission_map={"admin": ["*"]},
    )
    from backend.core import auth as auth_module

    app.dependency_overrides[auth_module._default_key_store] = lambda: store  # type: ignore[attr-defined]

    with patch("backend.routers.cts.settings", cfg):
        yield app


@pytest.fixture
def client_on():
    from unittest.mock import patch

    cfg = Settings.from_dict(
        {
            "cts": {"enabled": True},
            "cts_ui": {
                "calibration_enabled": True,
                "dashboard_enabled": True,
                "live_view_enabled": False,
            },
        }
    )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )

    with patch("backend.routers.cts.settings", cfg), TestClient(app) as c:
        yield c


@pytest.fixture
def client_off():
    from unittest.mock import patch

    cfg = Settings.from_dict(
        {
            "cts": {"enabled": False},
            "cts_ui": {
                "calibration_enabled": False,
                "dashboard_enabled": False,
                "live_view_enabled": False,
            },
        }
    )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )

    with patch("backend.routers.cts.settings", cfg), TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCTSStatus:
    def test_status_returns_enabled_true(self, client_on: TestClient):
        r = client_on.get("/api/v1/cts/status")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is True
        assert "calibration_enabled" in body
        assert "dashboard_enabled" in body

    def test_status_returns_enabled_false(self, client_off: TestClient):
        r = client_off.get("/api/v1/cts/status")
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_features_returns_dict(self, client_on: TestClient):
        r = client_on.get("/api/v1/cts/features")
        assert r.status_code == 200
        body = r.json()
        assert "calibration" in body
        assert "live_view" in body
        assert "signals_dashboard" in body
