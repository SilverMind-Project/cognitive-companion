"""Tests for the CTS calibration router and homography math."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401
from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import Base, get_db
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_calibration import compute_homography, router

# ---------------------------------------------------------------------------
# Pure-function tests: compute_homography
# ---------------------------------------------------------------------------


class TestComputeHomography:
    """Validate the homography math without FastAPI in the loop."""

    @pytest.fixture(autouse=True)
    def _skip_no_cv2(self):
        pytest.importorskip("cv2", reason="opencv-python-headless not installed")

    def _identity_points(self):
        """4 points on an identity transform (pixel == floor_m)."""
        pts = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        return pts, pts

    def test_identity_transform_zero_residuals(self):
        px, fl = self._identity_points()
        matrix, residuals = compute_homography(px, fl)
        assert len(matrix) == 3
        assert all(len(row) == 3 for row in matrix)
        assert all(r < 1e-6 for r in residuals), f"Expected near-zero residuals, got {residuals}"

    def test_scale_transform(self):
        pixel = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]]
        floor = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]]
        _, residuals = compute_homography(pixel, floor)
        assert all(r < 0.01 for r in residuals)

    def test_raises_with_fewer_than_4_points(self):
        with pytest.raises(ValueError, match="At least 4"):
            compute_homography([[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 0], [1, 1]])

    def test_returns_float_matrix(self):
        px, fl = self._identity_points()
        matrix, _ = compute_homography(px, fl)
        assert all(isinstance(v, float) for row in matrix for v in row)


# ---------------------------------------------------------------------------
# Router fixtures
# ---------------------------------------------------------------------------


def _make_client(cts_enabled: bool = True) -> TestClient:
    from unittest.mock import AsyncMock, MagicMock, patch

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

    # Fake orchestrator that succeeds silently.
    orchestrator = MagicMock()
    orchestrator.post_homography = AsyncMock(return_value={})
    orchestrator.post_privacy_zones = AsyncMock(return_value=None)
    orchestrator.post_adjacency = AsyncMock(return_value=None)
    orchestrator.post_reload = AsyncMock(return_value=None)
    orchestrator.calibration_status = AsyncMock(return_value={"adjacency_edge_count": 0})

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.state.orchestrator_client = orchestrator

    patcher = patch("backend.routers.cts_calibration.settings", cfg)
    patcher.start()
    client = TestClient(app)
    client._patcher = patcher  # type: ignore[attr-defined]
    client._orchestrator = orchestrator  # type: ignore[attr-defined]
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


@pytest.fixture
def camera_id(client: TestClient) -> str:
    """Seed a camera so calibration endpoints have a target."""
    from backend.models.cts_camera import CtsCamera

    # Access the real DB session from the override.
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        cam = CtsCamera(id="cal-cam", name="CalibrationCam", rtsp_url="rtsp://x")
        db.add(cam)
        db.commit()
    finally:
        import contextlib

        with contextlib.suppress(StopIteration):
            next(db_gen)
    return "cal-cam"


# ---------------------------------------------------------------------------
# Homography endpoint
# ---------------------------------------------------------------------------

POINTS = [
    {"pixel": [0.2, 0.8], "floor_m": [1.0, 3.5]},
    {"pixel": [0.8, 0.8], "floor_m": [4.0, 3.5]},
    {"pixel": [0.8, 0.2], "floor_m": [4.0, 0.5]},
    {"pixel": [0.2, 0.2], "floor_m": [1.0, 0.5]},
]


class TestHomographyEndpoint:
    @pytest.mark.skipif(
        not pytest.importorskip("cv2", reason="opencv not installed"),
        reason="opencv-python-headless not installed",
    )
    def test_post_homography_success(self, client: TestClient, camera_id: str):
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
