"""Tests for the CTS calibration BFF router.

Homography computation now runs in the tracking orchestrator.  The CC router
is a thin proxy that delegates to orchestrator.fit_homography() and persists
the result to the local DB.  These tests validate the proxy contract and the
endpoints that remain in CC (privacy zones, adjacency, auto-calibrate).

Pure-function tests for compute_homography / FloorPlaneFitter / AutoCalibrator
live in the orchestrator's own test suite.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401
from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_calibration import router

# ---------------------------------------------------------------------------
# Router fixture helpers
# ---------------------------------------------------------------------------


def _make_client(
    db_engine: Engine,
    cts_enabled: bool = True,
    fit_result: dict | None = None,
    *,
    db_session: Session | None = None,
) -> TestClient:
    """Build a TestClient with a mocked orchestrator for calibration tests."""
    from unittest.mock import AsyncMock, MagicMock, patch

    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def _override_db():
        # Reuse the provided db_session if given (triggers _truncate_tables).
        db = db_session or Session()
        try:
            yield db
        finally:
            if db_session is None:
                db.close()

    # Default fit result: a clean 4-point calibration with zero residuals.
    default_fit = {
        "camera_id": "cal-cam",
        "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "residuals_m": [0.001, 0.001, 0.001, 0.001],
        "max_residual_m": 0.001,
        "status": "ok",
    }

    orchestrator = MagicMock()
    orchestrator.fit_homography = AsyncMock(return_value=fit_result or default_fit)
    orchestrator.auto_calibrate = AsyncMock(
        return_value={
            "camera_id": "cal-cam",
            "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "confidence": 0.75,
            "inlier_count": 1200,
            "sample_count": 2048,
            "fov_deg": 70.0,
            "method": "depth_auto",
            "warning": None,
        }
    )
    orchestrator.post_privacy_zones = AsyncMock(return_value=None)
    orchestrator.post_adjacency = AsyncMock(return_value=None)
    orchestrator.post_reload = AsyncMock(return_value=None)
    orchestrator.calibration_status = AsyncMock(return_value={"adjacency_edge_count": 0})

    ingress = MagicMock()
    ingress.snapshot = AsyncMock(return_value=b"\xff\xd8\xff\xe0fake-jpeg")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.state.orchestrator_client = orchestrator
    app.state.ingress_admin_client = ingress

    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    client = TestClient(app)
    client._patcher = patcher  # type: ignore[attr-defined]
    client._orchestrator = orchestrator  # type: ignore[attr-defined]
    return client


@pytest.fixture
def client(db_engine: Engine, db_session: Session):
    """TestClient wired to the shared db_session so _truncate_tables fires."""
    c = _make_client(db_engine, cts_enabled=True, db_session=db_session)
    yield c
    c._patcher.stop()  # type: ignore[attr-defined]


@pytest.fixture
def client_off(db_engine: Engine, db_session: Session):
    c = _make_client(db_engine, cts_enabled=False, db_session=db_session)
    yield c
    c._patcher.stop()  # type: ignore[attr-defined]


@pytest.fixture
def camera_id(db_session: Session, client: TestClient) -> str:
    """Seed a camera so calibration endpoints have a target."""
    from backend.models.cts_camera import CtsCamera

    cam = CtsCamera(id="cal-cam", name="CalibrationCam", rtsp_url="rtsp://x")
    db_session.add(cam)
    db_session.commit()
    return "cal-cam"


# ---------------------------------------------------------------------------
# Homography proxy endpoint
# ---------------------------------------------------------------------------


POINTS = [
    {"pixel": [0.2, 0.8], "floor_m": [1.0, 3.5]},
    {"pixel": [0.8, 0.8], "floor_m": [4.0, 3.5]},
    {"pixel": [0.8, 0.2], "floor_m": [4.0, 0.5]},
    {"pixel": [0.2, 0.2], "floor_m": [1.0, 0.5]},
]


class TestHomographyEndpoint:
    def test_post_homography_success_proxies_to_orchestrator(
        self, client: TestClient, camera_id: str
    ):
        """CC should call orchestrator.fit_homography and return the result."""
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json={"camera_id": camera_id, "points": POINTS},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["camera_id"] == camera_id
        assert len(body["matrix"]) == 3
        assert body["max_residual_m"] >= 0.0
        assert body["status"] in ("ok", "warning", "error")
        # Verify the orchestrator was called (not local cv2).
        client._orchestrator.fit_homography.assert_called_once()  # type: ignore[attr-defined]

    def test_post_homography_persists_to_db(
        self, client: TestClient, camera_id: str, db_session: Session
    ):
        """After a successful call the camera row must have homography set."""
        from backend.models.cts_camera import CtsCamera

        client.post(
            "/api/v1/cts/calibration/homography",
            json={"camera_id": camera_id, "points": POINTS},
        )
        db_session.expire_all()
        cam = db_session.get(CtsCamera, camera_id)
        assert cam is not None
        assert cam.homography is not None
        assert "matrix" in cam.homography

    def test_missing_camera_returns_404(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json={"camera_id": "does-not-exist", "points": POINTS},
        )
        assert r.status_code == 404

    def test_too_few_points_returns_422(self, client: TestClient, camera_id: str):
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json={"camera_id": camera_id, "points": POINTS[:3]},
        )
        assert r.status_code == 422

    def test_cts_disabled_returns_404(self, client_off: TestClient):
        r = client_off.post(
            "/api/v1/cts/calibration/homography",
            json={"camera_id": "x", "points": POINTS},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "cts.disabled"


# ---------------------------------------------------------------------------
# Auto-calibrate endpoint
# ---------------------------------------------------------------------------


class TestAutoCalibrate:
    def test_auto_calibrate_success(self, client: TestClient, camera_id: str):
        r = client.post(
            f"/api/v1/cts/calibration/auto/{camera_id}",
            json={"minio_key": "frames/cam1/0001.jpg", "fov_deg": 70.0},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["camera_id"] == camera_id
        assert body["method"] == "depth_auto"
        assert 0.0 <= body["confidence"] <= 1.0
        assert body["inlier_count"] > 0

    def test_auto_calibrate_persists_to_db(
        self, client: TestClient, camera_id: str, db_session: Session
    ):
        from backend.models.cts_camera import CtsCamera

        client.post(
            f"/api/v1/cts/calibration/auto/{camera_id}",
            json={"minio_key": "frames/cam1/0001.jpg"},
        )
        db_session.expire_all()
        cam = db_session.get(CtsCamera, camera_id)
        assert cam is not None
        assert cam.homography is not None
        assert cam.homography.get("method") == "depth_auto"

    def test_auto_calibrate_missing_camera_returns_404(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/auto/ghost-cam",
            json={"minio_key": "frames/x/1.jpg"},
        )
        assert r.status_code == 404

    def test_auto_calibrate_without_minio_key_uses_ingress_snapshot(
        self, client: TestClient, camera_id: str
    ):
        """When minio_key is omitted the BFF should fetch a fresh ingress snapshot."""
        r = client.post(
            f"/api/v1/cts/calibration/auto/{camera_id}",
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["camera_id"] == camera_id
        assert body["method"] == "depth_auto"
        # Orchestrator must have been called with snapshot_bytes, not minio_key.
        call_kwargs = client._orchestrator.auto_calibrate.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs.get("snapshot_bytes") is not None
        assert call_kwargs.get("minio_key") is None

    def test_auto_calibrate_cts_disabled_returns_404(self, client_off: TestClient):
        r = client_off.post(
            "/api/v1/cts/calibration/auto/any-cam",
            json={"minio_key": "frames/x/1.jpg"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "cts.disabled"


# ---------------------------------------------------------------------------
# Privacy zones endpoint
# ---------------------------------------------------------------------------


ZONE = {
    "zone_id": "z1",
    "name": "Bathroom",
    "polygon": [[0.0, 0.5], [1.0, 0.5], [1.0, 1.0], [0.0, 1.0]],
    "policy": "mask_region",
    "enabled": True,
}


class TestPrivacyZonesEndpoint:
    def test_post_zones_accepted(self, client: TestClient, camera_id: str):
        r = client.post(
            "/api/v1/cts/calibration/privacy_zones",
            json={"camera_id": camera_id, "zones": [ZONE]},
        )
        assert r.status_code == 204

    def test_get_zones_after_post(self, client: TestClient, camera_id: str):
        client.post(
            "/api/v1/cts/calibration/privacy_zones",
            json={"camera_id": camera_id, "zones": [ZONE]},
        )
        r = client.get(f"/api/v1/cts/calibration/privacy_zones/{camera_id}")
        assert r.status_code == 200
        assert len(r.json()["zones"]) == 1

    def test_invalid_policy_rejected(self, client: TestClient, camera_id: str):
        zone = {**ZONE, "policy": "delete_everything"}
        r = client.post(
            "/api/v1/cts/calibration/privacy_zones",
            json={"camera_id": camera_id, "zones": [zone]},
        )
        assert r.status_code == 422

    def test_out_of_range_coords_rejected(self, client: TestClient, camera_id: str):
        zone = {**ZONE, "polygon": [[0.0, 0.0], [2.0, 0.0], [1.0, 1.0]]}
        r = client.post(
            "/api/v1/cts/calibration/privacy_zones",
            json={"camera_id": camera_id, "zones": [zone]},
        )
        assert r.status_code == 422

    def test_missing_camera_returns_404(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/privacy_zones",
            json={"camera_id": "ghost", "zones": [ZONE]},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Adjacency endpoint
# ---------------------------------------------------------------------------


EDGE = {"from": "hallway", "to": "kitchen", "min_transit_s": 1.0, "max_transit_s": 20.0}


class TestAdjacencyEndpoint:
    def test_post_adjacency_accepted(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/adjacency",
            json={"edges": [EDGE]},
        )
        assert r.status_code == 204

    def test_inverted_transit_rejected(self, client: TestClient):
        bad_edge = {**EDGE, "min_transit_s": 30.0, "max_transit_s": 1.0}
        r = client.post(
            "/api/v1/cts/calibration/adjacency",
            json={"edges": [bad_edge]},
        )
        assert r.status_code == 422
        assert "max_transit_s" in r.json()["detail"]["message"]

    def test_default_transit_bounds_accepted(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/adjacency",
            json={"edges": [{"from": "a", "to": "b"}]},
        )
        assert r.status_code == 204

    def test_get_adjacency_returns_count(self, client: TestClient):
        client.post("/api/v1/cts/calibration/adjacency", json={"edges": [EDGE]})
        r = client.get("/api/v1/cts/calibration/adjacency")
        assert r.status_code == 200
        assert "edge_count" in r.json()
