"""The run_companion_surface_test MCP tool and POST /companion-surfaces/{id}/test share
one service function, so both send the same command and report the same outcome."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.models  # noqa: F401 - ensure all ORM models are registered
from backend.core.auth import AuthContext, get_auth_context
from backend.core.exceptions import register_exception_handlers
from backend.mcp import server as mcp_server
from backend.models.companion_surface import CompanionSurface
from backend.routers import companion_surfaces
from backend.routers.dependencies import get_companion_surface_service
from backend.services.companion_surface import CompanionSurfaceService


class _RecordingSocketManager:
    def __init__(self) -> None:
        self.commands: list = []

    async def send_hardware_command(self, command) -> int:
        self.commands.append(command)
        return 1


def _seed(db_session, surface_id: str, *, enabled: bool = True) -> None:
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


def _comparable(command) -> dict:
    return command.model_dump(exclude={"server_timestamp"})


def test_router_and_mcp_send_the_same_command_and_result(db_factory, db_session, monkeypatch):
    _seed(db_session, "kitchen-tablet")
    manager = _RecordingSocketManager()
    svc = CompanionSurfaceService(db_factory=db_factory, ws_manager=manager)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(companion_surfaces.router, prefix="/api/v1")
    app.dependency_overrides[get_companion_surface_service] = lambda: svc
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        key="c", name="Caregiver", roles=["caregiver"]
    )
    monkeypatch.setattr(mcp_server._svc, "companion_surfaces", svc, raising=False)

    via_router = TestClient(app).post(
        "/api/v1/companion-surfaces/kitchen-tablet/test", json={"microphone": True}
    )
    via_mcp = asyncio.run(mcp_server.run_companion_surface_test("kitchen-tablet", microphone=True))

    assert via_router.status_code == 200
    assert via_router.json() == via_mcp
    router_command, mcp_command = manager.commands
    assert _comparable(router_command) == _comparable(mcp_command)


def test_mcp_reports_an_unknown_or_disabled_surface_as_an_error(
    db_factory, db_session, monkeypatch
):
    _seed(db_session, "old-tablet", enabled=False)
    manager = _RecordingSocketManager()
    svc = CompanionSurfaceService(db_factory=db_factory, ws_manager=manager)
    monkeypatch.setattr(mcp_server._svc, "companion_surfaces", svc, raising=False)

    unknown = asyncio.run(mcp_server.run_companion_surface_test("nowhere"))
    disabled = asyncio.run(mcp_server.run_companion_surface_test("old-tablet"))

    assert "not found" in unknown["error"]
    assert "disabled" in disabled["error"]
    assert manager.commands == []


def test_the_tool_needs_the_same_token_as_the_route():
    assert mcp_server.tool_token("run_companion_surface_test") == "companion_surfaces.test:execute"


def test_the_voice_companion_can_never_call_the_screen_test():
    """The resident's voice model must not wake screens or open microphones itself:
    the tool is a caregiver action, so it stays off the voice agent's allowlist."""
    from backend.core.config import settings

    assert "run_companion_surface_test" not in settings.as_list("mcp.gemini_tools")
