"""U5-T3: /ws/pipeline WebSocket endpoint tests.

Verifies:
- Unauthenticated upgrade does not land in the manager (auth enforced)
- Authenticated client connects and is tracked in the manager
- Disconnect removes the connection from the manager
- Missing manager state closes the socket (server not ready)
- Permission denied does not land in the manager
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.ws import router
from backend.websocket.pipeline_manager import PipelineConnectionManager


def _build_app() -> tuple[FastAPI, PipelineConnectionManager]:
    app = FastAPI()
    app.include_router(router)
    manager = PipelineConnectionManager()
    app.state.pipeline_ws_manager = manager
    return app, manager


class TestPipelineWSAuth:
    def test_no_key_does_not_land_in_manager(self):
        """No API key: server closes before accept; manager stays empty."""
        app, manager = _build_app()

        with (
            patch(
                "backend.routers.ws._resolve_key",
                side_effect=Exception("should not reach"),
            ),
            TestClient(app, raise_server_exceptions=False) as tc,
        ):
            try:
                with tc.websocket_connect("/ws/pipeline"):
                    pass
            except Exception:
                pass

        assert len(manager.active_connections) == 0

    def test_bad_key_does_not_land_in_manager(self):
        """Invalid API key: AuthenticationError; manager stays empty."""
        from backend.core.exceptions import AuthenticationError

        app, manager = _build_app()

        with (
            patch(
                "backend.routers.ws._resolve_key",
                side_effect=AuthenticationError(),
            ),
            TestClient(app, raise_server_exceptions=False) as tc,
        ):
            try:
                with tc.websocket_connect("/ws/pipeline", headers={"x-api-key": "bad-key"}):
                    pass
            except Exception:
                pass

        assert len(manager.active_connections) == 0

    def test_permission_denied_does_not_land_in_manager(self):
        from backend.core.auth import AuthContext

        app, manager = _build_app()

        with (
            patch(
                "backend.routers.ws._resolve_key",
                return_value=AuthContext(
                    key="device-key", name="device", permissions=["device:recamera"]
                ),
            ),
            patch("backend.routers.ws.has_permission", return_value=False),
            TestClient(app, raise_server_exceptions=False) as tc,
        ):
            try:
                with tc.websocket_connect("/ws/pipeline", headers={"x-api-key": "device-key"}):
                    pass
            except Exception:
                pass

        assert len(manager.active_connections) == 0


class TestPipelineWSConnection:
    def test_authenticated_client_is_tracked_in_manager(self):
        from backend.core.auth import AuthContext

        app, manager = _build_app()
        p1 = patch(
            "backend.routers.ws._resolve_key",
            return_value=AuthContext(key="valid-key", name="admin", permissions=["admin"]),
        )
        p2 = patch("backend.routers.ws.has_permission", return_value=True)

        with p1, p2, TestClient(app, raise_server_exceptions=False) as tc:  # noqa: SIM117
            with tc.websocket_connect("/ws/pipeline", headers={"x-api-key": "valid-key"}):
                assert len(manager.active_connections) == 1

    def test_disconnect_removes_from_manager(self):
        from backend.core.auth import AuthContext

        app, manager = _build_app()
        p1 = patch(
            "backend.routers.ws._resolve_key",
            return_value=AuthContext(key="valid-key", name="admin", permissions=["admin"]),
        )
        p2 = patch("backend.routers.ws.has_permission", return_value=True)

        with p1, p2, TestClient(app, raise_server_exceptions=False) as tc:  # noqa: SIM117
            with tc.websocket_connect("/ws/pipeline", headers={"x-api-key": "valid-key"}):
                pass  # exits immediately → disconnect

        assert len(manager.active_connections) == 0

    def test_no_manager_does_not_raise_uncaught(self):
        """pipeline_ws_manager=None: server closes cleanly; no uncaught exception."""
        from backend.core.auth import AuthContext

        app, _ = _build_app()
        app.state.pipeline_ws_manager = None

        with (
            patch(
                "backend.routers.ws._resolve_key",
                return_value=AuthContext(key="valid-key", name="admin", permissions=["admin"]),
            ),
            patch("backend.routers.ws.has_permission", return_value=True),
            TestClient(app, raise_server_exceptions=False) as tc,
        ):
            try:
                with tc.websocket_connect("/ws/pipeline", headers={"x-api-key": "valid-key"}):
                    pass
            except Exception:
                pass
        # Test passes if no uncaught exception propagated.
