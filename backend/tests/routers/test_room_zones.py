"""Router tests for sub-room zones."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.models.room import Room
from backend.routers import room_zones
from backend.routers.dependencies import get_zone_service
from backend.services.person_location.types import FloorPoint
from backend.services.zones import ZoneService


@dataclass(frozen=True)
class _Location:
    room_id: int


class _PersonLocation:
    def __init__(self, *, location: _Location | None, floor_point: FloorPoint | None) -> None:
        self.location = location
        self.floor_point = floor_point

    async def where_is(self, person_id: str) -> _Location | None:
        return self.location

    async def latest_floor_point(self, person_id: str, *, max_age_s: int = 30) -> FloorPoint | None:
        return self.floor_point


def _add_room(db_session, name: str) -> Room:
    room = Room(name=name)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)
    return room


def _client(
    db_factory,
    auth: AuthContext | None = None,
    person_location: _PersonLocation | None = None,
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    svc = ZoneService(db_factory=db_factory, person_location_service=person_location)
    app.state.zone_service = svc
    app.include_router(room_zones.router, prefix="/api/v1")
    app.dependency_overrides[get_zone_service] = lambda: svc
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def _admin() -> AuthContext:
    return AuthContext(key="admin", name="Admin", permissions=["admin"])


def test_crud_roundtrip_pagination_shape(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    client = _client(db_factory, _admin())

    create = client.post(
        f"/api/v1/rooms/{room.id}/zones",
        json={
            "name": "sink",
            "purpose": "task_area",
            "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            "camera_ids": ["kitchen-cam-1"],
        },
    )
    listed = client.get(f"/api/v1/rooms/{room.id}/zones")
    zone_id = create.json()["id"]
    patched = client.patch(f"/api/v1/zones/{zone_id}", json={"name": "counter"})
    deleted = client.delete(f"/api/v1/zones/{zone_id}")
    listed_after_delete = client.get(f"/api/v1/rooms/{room.id}/zones")

    assert create.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["name"] == "sink"
    assert patched.status_code == 200
    assert patched.json()["name"] == "counter"
    assert deleted.status_code == 204
    assert listed_after_delete.json() == {"items": [], "total": 0}


def test_zone_routes_require_permission(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    client = _client(db_factory)

    responses = [
        client.get(f"/api/v1/rooms/{room.id}/zones"),
        client.post(
            f"/api/v1/rooms/{room.id}/zones",
            json={"name": "sink", "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]},
        ),
        client.patch("/api/v1/zones/1", json={"name": "sink"}),
        client.delete("/api/v1/zones/1"),
        client.get("/api/v1/persons/person-1/current-zone"),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401, 401]


def test_current_zone_endpoint_returns_zone(db_factory, db_session) -> None:
    room = _add_room(db_session, "Kitchen")
    person_location = _PersonLocation(
        location=_Location(room_id=room.id),
        floor_point=FloorPoint(x_m=0.5, y_m=0.5),
    )
    client = _client(db_factory, _admin(), person_location)
    created = client.post(
        f"/api/v1/rooms/{room.id}/zones",
        json={"name": "sink", "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]},
    )

    response = client.get("/api/v1/persons/person-1/current-zone")

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json()["name"] == "sink"


def test_auth_yaml_covers_room_zone_routes() -> None:
    data = yaml.safe_load(Path("config/auth.yaml").read_text())
    permission_map = data["permission_map"]

    assert "GET /api/v1/rooms/*/zones" in permission_map["room_zones:read"]
    assert "GET /api/v1/persons/*/current-zone" in permission_map["room_zones:read"]
    assert "POST /api/v1/rooms/*/zones" in permission_map["room_zones:write"]
    assert "PATCH /api/v1/zones/*" in permission_map["room_zones:write"]
    assert "DELETE /api/v1/zones/*" in permission_map["room_zones:write"]
