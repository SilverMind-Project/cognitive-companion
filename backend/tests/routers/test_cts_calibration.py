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
            "draft_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "suggested_points": [
                {"pixel": [100.0, 300.0], "local_floor_m": [-0.5, 0.2]},
                {"pixel": [300.0, 420.0], "local_floor_m": [0.4, 1.1]},
            ],
            "confidence": 0.75,
            "inlier_count": 1200,
            "sample_count": 2048,
            "fov_deg": 70.0,
            "image_width": 640,
            "image_height": 480,
            "method": "depth_auto_draft",
            "warning": None,
            "floor_region_polygon": [[0.2, 0.4], [0.8, 0.4], [0.8, 0.9], [0.2, 0.9]],
        }
    )
    orchestrator.post_homography = AsyncMock(return_value=None)
    orchestrator.post_privacy_zones = AsyncMock(return_value=None)
    orchestrator.post_adjacency = AsyncMock(return_value=None)
    orchestrator.post_reload = AsyncMock(return_value=None)
    orchestrator.calibration_status = AsyncMock(return_value={"adjacency_edge_count": 0})

    ingress = MagicMock()
    ingress.snapshot = AsyncMock(return_value=b"\xff\xd8\xff\xe0fake-jpeg")

    minio = MagicMock()
    minio.async_upload_bytes = AsyncMock(return_value=None)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="x", name="tester", permissions=["*"]
    )
    app.state.orchestrator_client = orchestrator
    app.state.ingress_admin_client = ingress
    app.state.minio_client = minio

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


def _homography_payload(camera_id: str, points: list[dict] | None = None) -> dict:
    return {
        "camera_id": camera_id,
        "points": points or POINTS,
        "image_width": 640,
        "image_height": 480,
    }


class TestHomographyEndpoint:
    def test_post_homography_success_proxies_to_orchestrator(
        self, client: TestClient, camera_id: str
    ):
        """CC should call orchestrator.fit_homography and return the result."""
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json=_homography_payload(camera_id),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["camera_id"] == camera_id
        assert len(body["matrix"]) == 3
        assert body["max_residual_m"] >= 0.0
        assert body["status"] in ("ok", "warning", "error")
        # Verify the orchestrator was called (not local cv2).
        client._orchestrator.fit_homography.assert_called_once()  # type: ignore[attr-defined]
        client._orchestrator.post_homography.assert_called_once()  # type: ignore[attr-defined]

    def test_post_homography_pushes_committed_runtime_payload(
        self, client: TestClient, camera_id: str
    ):
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json=_homography_payload(camera_id),
        )

        assert r.status_code == 200
        call_kwargs = client._orchestrator.post_homography.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs["camera_id"] == camera_id
        assert call_kwargs["floor_plan_id"] == "household:1"
        assert call_kwargs["image_width"] == 640
        assert call_kwargs["image_height"] == 480
        assert call_kwargs["max_residual_m"] == pytest.approx(0.001)
        assert call_kwargs["mean_residual_m"] == pytest.approx(0.001)
        assert call_kwargs["quality_status"] == "ok"
        assert call_kwargs["quality_point_count"] == 4

    def test_post_homography_persists_to_db(
        self, client: TestClient, camera_id: str, db_session: Session
    ):
        """After a successful call the camera row must have homography set."""
        from backend.models.cts_camera import CtsCamera

        client.post(
            "/api/v1/cts/calibration/homography",
            json=_homography_payload(camera_id),
        )
        db_session.expire_all()
        cam = db_session.get(CtsCamera, camera_id)
        assert cam is not None
        assert cam.homography is not None
        assert "matrix" in cam.homography

    def test_missing_camera_returns_404(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json=_homography_payload("does-not-exist"),
        )
        assert r.status_code == 404

    def test_too_few_points_returns_422(self, client: TestClient, camera_id: str):
        r = client.post(
            "/api/v1/cts/calibration/homography",
            json=_homography_payload(camera_id, POINTS[:3]),
        )
        assert r.status_code == 422

    def test_cts_disabled_returns_404(self, client_off: TestClient):
        r = client_off.post(
            "/api/v1/cts/calibration/homography",
            json=_homography_payload("x"),
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
        assert body["method"] == "depth_auto_draft"
        assert len(body["draft_matrix"]) == 3
        assert len(body["suggested_points"]) == 2
        assert 0.0 <= body["confidence"] <= 1.0
        assert body["inlier_count"] > 0

    def test_auto_calibrate_does_not_persist_homography(
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
        assert cam.homography is None
        assert cam.homography_matrix is None
        assert cam.homography_method is None
        assert cam.visibility_polygon is None
        assert cam.snapshot_width == 640
        assert cam.snapshot_height == 480

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
        assert body["method"] == "depth_auto_draft"
        # Orchestrator must have been called with snapshot_bytes, not minio_key.
        call_kwargs = client._orchestrator.auto_calibrate.call_args.kwargs  # type: ignore[attr-defined]
        assert call_kwargs.get("snapshot_bytes") is not None
        assert call_kwargs.get("minio_key") is None

    def test_legacy_depth_auto_homography_is_uncommitted(
        self, client: TestClient, camera_id: str, db_session: Session
    ):
        from backend.models.cts_camera import CtsCamera

        cam = db_session.get(CtsCamera, camera_id)
        assert cam is not None
        cam.homography = {
            "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "method": "depth_auto",
        }
        db_session.commit()

        r = client.get(f"/api/v1/cts/calibration/homography/{camera_id}")

        assert r.status_code == 404

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


# ---------------------------------------------------------------------------
# Floor-region polygon endpoints
# ---------------------------------------------------------------------------

_FLOOR_REGION = [[0.2, 0.4], [0.8, 0.4], [0.8, 0.9], [0.2, 0.9]]


class TestFloorRegionEndpoint:
    def test_auto_calibrate_stores_floor_region_polygon(
        self, client: TestClient, camera_id: str, db_session: Session
    ):
        """auto-calibrate response that includes floor_region_polygon persists it to the DB."""
        from backend.models.cts_camera import CtsCamera

        r = client.post(
            f"/api/v1/cts/calibration/auto/{camera_id}",
            json={"minio_key": "frames/cam1/0001.jpg"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["floor_region_polygon"] == _FLOOR_REGION

        db_session.expire_all()
        cam = db_session.get(CtsCamera, camera_id)
        assert cam is not None
        assert cam.floor_region_polygon == _FLOOR_REGION
        assert cam.floor_region_source == "depth_auto"
        assert cam.floor_region_set_at is not None

    def test_floor_region_endpoint_saves_manual(
        self, client: TestClient, camera_id: str, db_session: Session
    ):
        """POST /floor_region persists the polygon with source='manual'."""
        from backend.models.cts_camera import CtsCamera

        r = client.post(
            f"/api/v1/cts/calibration/floor_region/{camera_id}",
            json={"polygon": _FLOOR_REGION, "source": "manual"},
        )
        assert r.status_code == 204

        db_session.expire_all()
        cam = db_session.get(CtsCamera, camera_id)
        assert cam is not None
        assert cam.floor_region_polygon == _FLOOR_REGION
        assert cam.floor_region_source == "manual"
        assert cam.floor_region_set_at is not None

    def test_floor_region_endpoint_missing_camera_returns_404(self, client: TestClient):
        r = client.post(
            "/api/v1/cts/calibration/floor_region/ghost-cam",
            json={"polygon": _FLOOR_REGION},
        )
        assert r.status_code == 404

    def test_floor_region_endpoint_rejects_out_of_range_coords(
        self, client: TestClient, camera_id: str
    ):
        """Coordinates outside [0,1] are invalid (NOT floor-plan metres)."""
        r = client.post(
            f"/api/v1/cts/calibration/floor_region/{camera_id}",
            json={"polygon": [[0.2, 0.4], [1.8, 0.4], [0.8, 0.9]]},
        )
        assert r.status_code == 422

    def test_floor_region_endpoint_rejects_fewer_than_3_points(
        self, client: TestClient, camera_id: str
    ):
        r = client.post(
            f"/api/v1/cts/calibration/floor_region/{camera_id}",
            json={"polygon": [[0.2, 0.4], [0.8, 0.4]]},
        )
        assert r.status_code == 422

    def test_floor_region_triggers_visibility_refresh_when_committed_homography_present(
        self, client: TestClient, db_session: Session, db_engine: Engine
    ):
        """POST /floor_region recomputes visibility_polygon immediately when homography exists.

        Seeds a camera with a committed homography (scaling matrix: 640x480 px → 10x8 m)
        and floor plan settings, then saves a floor-region polygon via the endpoint.
        The endpoint calls _refresh_visibility_polygon with cam.floor_region_polygon, so
        visibility_polygon must be populated after the save.
        """
        from sqlalchemy.orm import sessionmaker

        from backend.models.cts_camera import CtsCamera
        from backend.models.household_settings import HouseholdSettings

        # Scaling homography: pixel (x_px, y_px) → floor metres (x_px * 10/640, y_px * 8/480).
        # Interior floor-region points all normalise to [0, 1] — within visibility bounds.
        scaling = [[10 / 640, 0.0, 0.0], [0.0, 8 / 480, 0.0], [0.0, 0.0, 1.0]]

        Sess = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
        with Sess() as setup_db:
            # Committed homography via homography_matrix column.
            setup_db.add(
                CtsCamera(
                    id="floor-cam",
                    name="FloorCam",
                    rtsp_url="rtsp://x",
                    homography_matrix=scaling,
                    snapshot_width=640,
                    snapshot_height=480,
                    frame_natural_width=640,
                    frame_natural_height=480,
                )
            )
            setup_db.add(
                HouseholdSettings(
                    id=1,
                    floor_plan_key="floor-plans/main.png",
                    floor_plan_width=1000,
                    floor_plan_height=800,
                    floor_meters_per_pixel=0.01,  # 10 m x 8 m
                )
            )
            setup_db.commit()

        r = client.post(
            "/api/v1/cts/calibration/floor_region/floor-cam",
            json={"polygon": _FLOOR_REGION, "source": "manual"},
        )
        assert r.status_code == 204

        db_session.expire_all()
        cam = db_session.get(CtsCamera, "floor-cam")
        assert cam is not None
        assert cam.floor_region_polygon == _FLOOR_REGION
        assert cam.visibility_polygon is not None, (
            "Visibility polygon should be recomputed using floor_region_polygon"
        )
