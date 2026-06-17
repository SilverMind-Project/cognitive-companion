"""Router tests for companion surfaces."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.models.companion_surface import CompanionSurface
from backend.models.room import Room
from backend.routers import companion_surfaces
from backend.routers.dependencies import get_companion_surface_service
from backend.services.companion_surface import CompanionSurfaceService


def _add_room(db_session, name: str) -> Room:
    room = Room(name=name)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    return room


def _client(db_factory, auth: AuthContext | None = None) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    svc = CompanionSurfaceService(db_factory=db_factory)
    app.state.companion_surface_service = svc
    app.include_router(companion_surfaces.router, prefix="/api/v1")
    app.dependency_overrides[get_companion_surface_service] = lambda: svc
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def test_list_requires_permission(db_factory):
    client = _client(db_factory)

    response = client.get("/api/v1/companion-surfaces")

    assert response.status_code == 401


def test_create_then_list_roundtrip(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    client = _client(db_factory, AuthContext(key="admin", name="Admin", permissions=["admin"]))

    create = client.post(
        "/api/v1/companion-surfaces",
        json={
            "id": "kitchen-tablet",
            "name": "Kitchen Tablet",
            "surface_type": "movable",
            "kind": "tablet",
            "room_id": room.id,
        },
    )
    listed = client.get("/api/v1/companion-surfaces")

    assert create.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == "kitchen-tablet"


def test_patch_room_sets_caregiver_source(db_factory, db_session):
    kitchen = _add_room(db_session, "Kitchen")
    living = _add_room(db_session, "Living")
    db_session.add(
        CompanionSurface(
            id="tablet",
            name="Tablet",
            surface_type="movable",
            room_id=kitchen.id,
            room_source="cts_inferred",
            kind="tablet",
            is_enabled=True,
            room_mismatch=True,
        )
    )
    db_session.commit()
    client = _client(db_factory, AuthContext(key="admin", name="Admin", permissions=["admin"]))

    response = client.patch("/api/v1/companion-surfaces/tablet", json={"room_id": living.id})

    assert response.status_code == 200
    body = response.json()
    assert body["room_id"] == living.id
    assert body["room_source"] == "caregiver"
    assert body["room_mismatch"] is False


def test_heartbeat_with_device_key_ok(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    db_session.add(
        CompanionSurface(
            id="tablet",
            name="Tablet",
            surface_type="movable",
            room_id=room.id,
            room_source="caregiver",
            kind="tablet",
            is_enabled=True,
            room_mismatch=False,
        )
    )
    db_session.commit()
    client = _client(
        db_factory,
        AuthContext(
            key="RTRM0001",
            name="Terminal",
            permissions=["device:reterminal"],
            device_type="reterminal",
            sensor_id="reterminal_living",
        ),
    )

    response = client.post(
        "/api/v1/companion-surfaces/tablet/heartbeat",
        json={"reported_room_id": room.id},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_heartbeat_without_key_rejected(db_factory, db_session):
    room = _add_room(db_session, "Kitchen")
    db_session.add(
        CompanionSurface(
            id="tablet",
            name="Tablet",
            surface_type="movable",
            room_id=room.id,
            room_source="caregiver",
            kind="tablet",
            is_enabled=True,
            room_mismatch=False,
        )
    )
    db_session.commit()
    client = _client(db_factory)

    response = client.post("/api/v1/companion-surfaces/tablet/heartbeat", json={})

    assert response.status_code == 401


def test_auth_yaml_covers_companion_surface_routes():
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    permission_map = data["permission_map"]

    assert "GET /api/v1/companion-surfaces*" in permission_map["companion_surfaces:read"]
    assert "POST /api/v1/companion-surfaces" in permission_map["companion_surfaces:write"]
    assert "PATCH /api/v1/companion-surfaces/*" in permission_map["companion_surfaces:write"]
    assert (
        "POST /api/v1/companion-surfaces/*/heartbeat"
        in permission_map["companion_surfaces:heartbeat"]
    )
    assert (
        "POST /api/v1/companion-surfaces/*/heartbeat"
        in permission_map["device:reterminal"]
    )
