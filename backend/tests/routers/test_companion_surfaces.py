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
    client = _client(db_factory, AuthContext(key="admin", name="Admin", roles=["admin"]))

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
    client = _client(db_factory, AuthContext(key="admin", name="Admin", roles=["admin"]))

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
            roles=["device_reterminal"],
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
    roles = data["roles"]

    assert "companion_surfaces:read" in roles["caregiver"]
    assert "companion_surfaces:write" in roles["caregiver"]
    assert "companion_surfaces:heartbeat" in roles["device_reterminal"]


class _RecordingSocketManager:
    """Records hardware commands; ``online`` surfaces count as reached."""

    def __init__(self, online: set[str]) -> None:
        self.online = online
        self.commands: list = []

    async def send_hardware_command(self, command) -> int:
        self.commands.append(command)
        return 1 if command.surface_id in self.online else 0


def _test_client(db_factory, manager, auth: AuthContext | None) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    svc = CompanionSurfaceService(db_factory=db_factory, ws_manager=manager)
    app.include_router(companion_surfaces.router, prefix="/api/v1")
    app.dependency_overrides[get_companion_surface_service] = lambda: svc
    if auth is not None:
        app.dependency_overrides[get_auth_context] = lambda: auth
    return TestClient(app, raise_server_exceptions=False)


def _add_surface(db_session, surface_id: str, *, enabled: bool = True) -> None:
    db_session.add(
        CompanionSurface(
            id=surface_id,
            name=surface_id,
            surface_type="fixed",
            kind="tablet",
            room_source="caregiver",
            is_enabled=enabled,
        )
    )
    db_session.commit()


_CAREGIVER = AuthContext(key="c", name="Caregiver", roles=["caregiver"])


def test_testing_a_surface_wakes_only_that_surface_with_a_short_screen_lease(
    db_factory, db_session
):
    _add_surface(db_session, "kitchen-tablet")
    manager = _RecordingSocketManager(online={"kitchen-tablet"})
    client = _test_client(db_factory, manager, _CAREGIVER)

    response = client.post("/api/v1/companion-surfaces/kitchen-tablet/test", json={})

    assert response.status_code == 200
    assert response.json() == {
        "surface_id": "kitchen-tablet",
        "reached": 1,
        "microphone": False,
        "lease_seconds": 30,
    }
    [command] = manager.commands
    assert command.surface_id == "kitchen-tablet"
    assert command.wake_screen is True
    assert command.enable_microphone is False
    assert command.enable_camera is False
    assert command.lease_seconds == 30
    # Its own lease owner, so a test never ends a delivery's lease on that screen.
    assert command.lease_owner == "surface_test:kitchen-tablet"


def test_testing_a_surface_can_open_its_microphone_for_the_lease(db_factory, db_session):
    _add_surface(db_session, "kitchen-tablet")
    manager = _RecordingSocketManager(online={"kitchen-tablet"})
    client = _test_client(db_factory, manager, _CAREGIVER)

    response = client.post(
        "/api/v1/companion-surfaces/kitchen-tablet/test", json={"microphone": True}
    )

    assert response.status_code == 200
    assert response.json()["microphone"] is True
    assert manager.commands[0].enable_microphone is True


def test_testing_an_offline_surface_reports_it_and_reaches_no_other_screen(db_factory, db_session):
    _add_surface(db_session, "kitchen-tablet")
    manager = _RecordingSocketManager(online={"bedroom-tablet"})
    client = _test_client(db_factory, manager, _CAREGIVER)

    response = client.post("/api/v1/companion-surfaces/kitchen-tablet/test")

    assert response.status_code == 200
    assert response.json()["reached"] == 0
    assert [c.surface_id for c in manager.commands] == ["kitchen-tablet"]


def test_testing_an_unknown_surface_is_404_and_sends_nothing(db_factory):
    manager = _RecordingSocketManager(online=set())
    client = _test_client(db_factory, manager, _CAREGIVER)

    response = client.post("/api/v1/companion-surfaces/nowhere/test", json={})

    assert response.status_code == 404
    assert manager.commands == []


def test_testing_a_disabled_surface_is_409_and_sends_nothing(db_factory, db_session):
    _add_surface(db_session, "old-tablet", enabled=False)
    manager = _RecordingSocketManager(online={"old-tablet"})
    client = _test_client(db_factory, manager, _CAREGIVER)

    response = client.post("/api/v1/companion-surfaces/old-tablet/test", json={})

    assert response.status_code == 409
    assert manager.commands == []


def test_testing_a_surface_needs_the_test_token(db_factory, db_session):
    _add_surface(db_session, "kitchen-tablet")
    manager = _RecordingSocketManager(online={"kitchen-tablet"})
    # A companion screen's own key may connect and heartbeat, but not wake other screens.
    screen = AuthContext(key="d", name="Kitchen screen", roles=["device_reterminal"])
    client = _test_client(db_factory, manager, screen)

    response = client.post("/api/v1/companion-surfaces/kitchen-tablet/test", json={})

    assert response.status_code == 403
    assert manager.commands == []


def test_the_test_role_holds_exactly_a_screens_tokens_plus_testing():
    auth = yaml.safe_load(Path("config/auth.yaml").read_text())
    roles = auth["roles"]

    assert set(roles["companion_test_device"]) == set(roles["device_reterminal"]) | {
        "companion_surfaces.test:execute"
    }
