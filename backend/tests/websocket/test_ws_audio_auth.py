"""``/ws/audio`` authentication, surface binding, and the browser subprotocol echo.

The companion socket carries resident prompts and opens microphones, so it needs a
key holding ``companion.audio:act``. A browser cannot set headers on a WebSocket and
offers the key as its ``Sec-WebSocket-Protocol``; the server must select that
subprotocol or the browser drops the connection (close 1006). That held for
``/ws/cts`` and ``/ws/pipeline`` too, which never echoed it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.core.auth import AuthContext
from backend.routers import cts_live
from backend.routers.ws import router
from backend.websocket.connection_manager import ConnectionManager
from backend.websocket.pipeline_manager import PipelineConnectionManager

_KEY = "tabletkey123"


class _Surfaces:
    def __init__(self, **surfaces: bool) -> None:
        self._surfaces = surfaces

    def get_surface(self, surface_id: str) -> SimpleNamespace | None:
        if surface_id not in self._surfaces:
            return None
        return SimpleNamespace(id=surface_id, is_enabled=self._surfaces[surface_id])


def _app(**surfaces: bool) -> tuple[FastAPI, ConnectionManager]:
    app = FastAPI()
    app.include_router(router)
    app.include_router(cts_live.router)
    manager = ConnectionManager()
    app.state.ws_manager = manager
    app.state.cts_ws_manager = ConnectionManager()
    app.state.pipeline_ws_manager = PipelineConnectionManager()
    app.state.realtime_provider = None
    app.state.conversation_manager = None
    app.state.gemini_adapter = None
    app.state.companion_surface_service = _Surfaces(**surfaces)
    return app, manager


@contextmanager
def _keys(*, granted: bool = True) -> Iterator[None]:
    auth = AuthContext(key=_KEY, name="Kitchen tablet", roles=["device_reterminal"])
    with (
        patch("backend.core.auth._resolve_key", return_value=auth),
        patch("backend.core.auth.has_token", return_value=granted),
    ):
        yield


def _close_reason(app: FastAPI, path: str, **kwargs) -> str:
    with TestClient(app) as tc, pytest.raises(WebSocketDisconnect) as closed:  # noqa: SIM117
        with tc.websocket_connect(path, **kwargs) as ws:
            ws.receive_json()
    return closed.value.reason


def test_audio_socket_requires_a_key() -> None:
    app, manager = _app()

    assert _close_reason(app, "/ws/audio") == "auth_required"
    assert manager.active_connections == []


def test_audio_socket_requires_the_companion_token() -> None:
    app, manager = _app()

    with _keys(granted=False):
        reason = _close_reason(app, "/ws/audio", headers={"x-api-key": _KEY})

    assert reason == "permission_denied"
    assert manager.active_connections == []


@pytest.mark.parametrize("surface_id", ["hallway-tablet", "retired-tablet"])
def test_an_unknown_or_disabled_surface_connects_without_room_routing(surface_id: str) -> None:
    """A stale kiosk setting must not cut the screen off; it just loses room routing."""
    app, manager = _app(**{"retired-tablet": False})

    with _keys(), TestClient(app) as tc:  # noqa: SIM117
        with tc.websocket_connect(
            f"/ws/audio?surface_id={surface_id}", headers={"x-api-key": _KEY}
        ):
            assert len(manager.active_connections) == 1
            assert not manager.is_surface_connected(surface_id)


def test_browser_key_is_echoed_and_the_surface_is_bound() -> None:
    app, manager = _app(**{"kitchen-tablet": True})

    with _keys(), TestClient(app) as tc:  # noqa: SIM117
        with tc.websocket_connect(
            "/ws/audio?surface_id=kitchen-tablet&platform=android_tablet", subprotocols=[_KEY]
        ) as ws:
            assert ws.accepted_subprotocol == _KEY
            assert manager.is_surface_connected("kitchen-tablet")

    assert not manager.is_surface_connected("kitchen-tablet")


def test_header_key_selects_no_subprotocol() -> None:
    app, manager = _app()

    with _keys(), TestClient(app) as tc:  # noqa: SIM117
        with tc.websocket_connect("/ws/audio", headers={"x-api-key": _KEY}) as ws:
            assert ws.accepted_subprotocol is None
            assert len(manager.active_connections) == 1


@pytest.mark.parametrize("path", ["/ws/pipeline", "/ws/cts"])
def test_admin_sockets_echo_the_browser_key(path: str) -> None:
    app, _ = _app()

    with (
        _keys(),
        patch.object(cts_live.settings, "as_bool", return_value=True),
        TestClient(app) as tc,
        tc.websocket_connect(path, subprotocols=[_KEY]) as ws,
    ):
        assert ws.accepted_subprotocol == _KEY


def test_cts_live_view_never_joins_the_companion_socket() -> None:
    """An admin live view is not a companion screen: it must not receive resident
    prompts or make a guided session think a tablet is open."""
    app, companion = _app()

    with (
        _keys(),
        patch.object(cts_live.settings, "as_bool", return_value=True),
        TestClient(app) as tc,
        tc.websocket_connect("/ws/cts", headers={"x-api-key": _KEY}),
    ):
        assert companion.has_connections is False
        assert len(app.state.cts_ws_manager.active_connections) == 1
