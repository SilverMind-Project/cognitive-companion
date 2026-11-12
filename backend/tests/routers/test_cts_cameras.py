"""Tests for the CTS cameras router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.routers.cts_cameras import router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(db_engine: Engine, cts_enabled: bool = True) -> TestClient:
    from unittest.mock import AsyncMock, MagicMock, patch

    cfg = Settings.from_dict({"cts": {"enabled": cts_enabled}})

    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

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

    ingress = MagicMock()
    ingress.test_connection = AsyncMock(return_value={"ok": True})
    ingress.snapshot = AsyncMock(return_value=b"\xff\xd8\xff")
    ingress.stream_health = AsyncMock(return_value={"status": "ok"})
    ingress.reload_camera = AsyncMock(return_value=None)
    app.state.ingress_admin_client = ingress
    app.state.orchestrator_client = None

    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    client = TestClient(app)
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


@pytest.fixture
def client(db_engine: Engine):
    c = _make_client(db_engine, cts_enabled=True)
    yield c
    c._patcher.stop()  # type: ignore[attr-defined]


@pytest.fixture
def client_off(db_engine: Engine):
    c = _make_client(db_engine, cts_enabled=False)
    yield c
    c._patcher.stop()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


CAMERA = {
    "id": "kitchen-cam-1",
    "name": "Kitchen",
    "rtsp_url": "rtsp://192.168.1.10/stream",
    "room_name": "Kitchen",
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

    def test_list_includes_homography_matrix_for_cts_sync(
        self, client: TestClient, db_engine: Engine
    ):
        from backend.models.cts_camera import CtsCamera
        from backend.models.household_settings import HouseholdSettings

        matrix = [[1.0, 0.0, 0.1], [0.0, 1.0, 0.2], [0.0, 0.0, 1.0]]
        Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
        with Session() as db:
            db.add(HouseholdSettings(id=1, floor_plan_key="floor-plans/main.png"))
            db.add(
                CtsCamera(
                    id="synced-cam",
                    name="Synced",
                    rtsp_url="rtsp://x",
                    room_name="Kitchen",
                    homography_matrix=matrix,
                    homography_residuals=[0.01, 0.02, 0.01, 0.02],
                    homography_residual_m=0.02,
                    homography_method="manual",
                    frame_natural_width=1920,
                    frame_natural_height=1080,
                )
            )
            db.commit()

        r = client.get("/api/v1/cts/cameras")

        assert r.status_code == 200
        body = r.json()[0]
        assert body["homography_matrix"] == matrix
        assert body["homography_residual_m"] == 0.02
        assert body["homography_method"] == "manual"
        assert body["homography_floor_plan_id"] == "floor-plans/main.png"
        assert body["frame_natural_width"] == 1920
        assert body["frame_natural_height"] == 1080
        assert body["privacy_zones"] == []

    def test_list_carries_saved_privacy_zones_for_cts_sync(
        self, client: TestClient, db_engine: Engine
    ):
        # The orchestrator keeps zones only in memory and restores them from this list.
        from backend.models.cts_camera import CtsCamera

        zone = {
            "zone_id": "mirror",
            "name": "Mirror",
            "polygon": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.5]],
            "policy": "drop_detection",
            "enabled": True,
        }
        Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
        with Session() as db:
            db.add(
                CtsCamera(id="zoned-cam", name="Zoned", rtsp_url="rtsp://x", privacy_zones=[zone])
            )
            db.commit()

        r = client.get("/api/v1/cts/cameras")

        assert r.status_code == 200
        body = r.json()[0]
        assert body["privacy_zones"] == [zone]
        assert body["privacy_zone_count"] == 1


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

    def test_legacy_depth_auto_is_not_reported_as_calibrated(
        self, client: TestClient, db_engine: Engine
    ):
        from backend.models.cts_camera import CtsCamera

        Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
        with Session() as db:
            db.add(
                CtsCamera(
                    id="legacy-depth-auto",
                    name="Legacy",
                    rtsp_url="rtsp://x",
                    homography={
                        "matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                        "method": "depth_auto",
                    },
                )
            )
            db.commit()

        r = client.get("/api/v1/cts/cameras/legacy-depth-auto")

        assert r.status_code == 200
        assert r.json()["has_homography"] is False


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


class TestFaceRawSimilarityFloor:
    def test_floor_defaults_to_unset(self, client: TestClient):
        body = client.post("/api/v1/cts/cameras", json=CAMERA).json()
        assert body["face_id_min_raw_similarity"] is None
        assert "face_id_min_confidence" not in body

    def test_floor_round_trips_and_clears(self, client: TestClient):
        client.post("/api/v1/cts/cameras", json={**CAMERA, "face_id_min_raw_similarity": 0.55})
        assert (
            client.get("/api/v1/cts/cameras/kitchen-cam-1").json()["face_id_min_raw_similarity"]
            == 0.55
        )

        r = client.patch(
            "/api/v1/cts/cameras/kitchen-cam-1", json={"face_id_min_raw_similarity": None}
        )

        assert r.status_code == 200
        assert r.json()["face_id_min_raw_similarity"] is None
        listed = client.get("/api/v1/cts/cameras").json()
        assert listed[0]["face_id_min_raw_similarity"] is None

    @pytest.mark.parametrize("value", [-0.1, 1.5])
    def test_out_of_range_floor_returns_422(self, client: TestClient, value: float):
        r = client.post("/api/v1/cts/cameras", json={**CAMERA, "face_id_min_raw_similarity": value})
        assert r.status_code == 422
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.patch(
            "/api/v1/cts/cameras/kitchen-cam-1", json={"face_id_min_raw_similarity": value}
        )
        assert r.status_code == 422

    def test_old_field_name_is_rejected(self, client: TestClient):
        r = client.post("/api/v1/cts/cameras", json={**CAMERA, "face_id_min_confidence": 0.6})
        assert r.status_code == 422
        client.post("/api/v1/cts/cameras", json=CAMERA)
        r = client.patch("/api/v1/cts/cameras/kitchen-cam-1", json={"face_id_min_confidence": 0.6})
        assert r.status_code == 422


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
