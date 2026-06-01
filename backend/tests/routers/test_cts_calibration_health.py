"""Tests for CTS calibration health diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.models.cts_camera import CtsCamera
from backend.routers.cts_calibration_health import router


def _make_client(db_engine: Engine) -> TestClient:
    cfg = Settings.from_dict({"cts": {"enabled": True}})
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
    orchestrator = MagicMock()
    orchestrator.calibration_status = AsyncMock(return_value={"homography_camera_ids": []})
    app.state.orchestrator_client = orchestrator

    patcher = patch("backend.routers.cts_deps.settings", cfg)
    patcher.start()
    client = TestClient(app)
    client._patcher = patcher  # type: ignore[attr-defined]
    return client


def test_calibration_health_reports_runtime_matrix_missing(db_engine: Engine):
    matrix = [[1.0, 0.0, 0.1], [0.0, 1.0, 0.2], [0.0, 0.0, 1.0]]
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.add(
            CtsCamera(
                id="calibrated-cam",
                name="Calibrated",
                rtsp_url="rtsp://x",
                enabled=True,
                homography_matrix=matrix,
                homography_residual_m=0.02,
            )
        )
        db.commit()

    client = _make_client(db_engine)
    try:
        response = client.get("/api/v1/cts/calibration/health")
    finally:
        client._patcher.stop()  # type: ignore[attr-defined]

    assert response.status_code == 200
    camera = response.json()["cameras"][0]
    assert camera["camera_id"] == "calibrated-cam"
    assert camera["homography_present"] is True
    assert camera["runtime_homography_present"] is False
    assert camera["severity"] == "error"
    assert camera["code"] == "runtime_matrix_missing"
