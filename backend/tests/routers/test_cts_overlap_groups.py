"""CTS overlap-group CRUD: the groups CTS reads on every config sync."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from backend.core.auth import AuthContext, get_auth_context
from backend.core.config import Settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.models.cts_camera import CtsCamera
from backend.routers.cts_overlap_groups import router


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.execute(text("DELETE FROM cts_camera_overlap_groups"))
        for camera_id in ("cam-a", "cam-b"):
            if db.get(CtsCamera, camera_id) is None:
                db.add(CtsCamera(id=camera_id, name=camera_id, rtsp_url="rtsp://x", enabled=True))
        db.commit()

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
    cfg = Settings.from_dict({"cts": {"enabled": True}})
    with patch("backend.routers.cts_deps.settings", cfg):
        yield TestClient(app)


def test_create_list_delete_round_trip(client: TestClient) -> None:
    created = client.post(
        "/api/v1/cts/overlap_groups", json={"name": "Living room", "camera_ids": ["cam-a", "cam-b"]}
    )
    assert created.status_code == 201
    group_id = created.json()["id"]

    listed = client.get("/api/v1/cts/overlap_groups").json()
    assert [(g["id"], g["camera_ids"]) for g in listed] == [(group_id, ["cam-a", "cam-b"])]

    assert client.delete(f"/api/v1/cts/overlap_groups/{group_id}").status_code == 204
    assert client.get("/api/v1/cts/overlap_groups").json() == []


def test_unknown_camera_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/cts/overlap_groups", json={"name": "Typo", "camera_ids": ["cam-a", "cam-z"]}
    )

    assert response.status_code == 422
    assert "cam-z" in response.text
    assert client.get("/api/v1/cts/overlap_groups").json() == []


def test_repeated_camera_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/cts/overlap_groups", json={"name": "Twice", "camera_ids": ["cam-a", "cam-a"]}
    )

    assert response.status_code == 422
    assert client.get("/api/v1/cts/overlap_groups").json() == []


def test_delete_missing_group_is_404(client: TestClient) -> None:
    assert client.delete("/api/v1/cts/overlap_groups/999999").status_code == 404


_SQUARE = [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]


def _set_polygons(db_engine: Engine, polygons: dict[str, list | None]) -> None:
    Session = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        for camera_id, polygon in polygons.items():
            db.get(CtsCamera, camera_id).visibility_polygon = polygon
        db.commit()


def test_suggestions_group_calibrated_cameras_with_shared_coverage(
    client: TestClient, db_engine: Engine
) -> None:
    _set_polygons(db_engine, {"cam-a": _SQUARE, "cam-b": _SQUARE})

    body = client.get("/api/v1/cts/overlap_groups/suggested").json()

    assert [(g["camera_ids"], g["declared"]) for g in body["groups"]] == [
        (["cam-a", "cam-b"], False)
    ]


def test_suggestion_marked_declared_once_a_group_covers_it(
    client: TestClient, db_engine: Engine
) -> None:
    _set_polygons(db_engine, {"cam-a": _SQUARE, "cam-b": _SQUARE})
    client.post(
        "/api/v1/cts/overlap_groups", json={"name": "Living room", "camera_ids": ["cam-b", "cam-a"]}
    )

    body = client.get("/api/v1/cts/overlap_groups/suggested").json()

    assert body["groups"][0]["declared"] is True


def test_uncalibrated_cameras_are_listed_not_suggested(
    client: TestClient, db_engine: Engine
) -> None:
    _set_polygons(db_engine, {"cam-a": None, "cam-b": None})

    body = client.get("/api/v1/cts/overlap_groups/suggested").json()

    assert body["groups"] == []
    assert {"cam-a", "cam-b"} <= set(body["uncalibrated_camera_ids"])
