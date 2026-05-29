"""CTS live-view WebSocket endpoint.

A read-only WebSocket for the ``CTSLiveView.vue`` dashboard. Clients
receive two kinds of messages:

- ``cts_live_frame``: broadcast by :class:`TrackingEventSubscriber` for each
  tracking event that contains at least one detection. Carries bbox + identity
  metadata for client-side overlay.
- ``cts_identity_revision``: broadcast by :class:`IdentityRewriter` when a
  revision is applied. Lets the client show a non-blocking toast and
  refresh affected rows.

Authentication: the upgrade request carries the same ``X-API-Key`` / query
param as REST endpoints. The fnmatch permission ``cts.live.subscribe`` is
required. When ``cts.enabled=False`` the upgrade is rejected with 1008
(Policy Violation) so clients can fail fast.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.auth import _resolve_key, has_permission
from backend.core.config import settings
from backend.core.exceptions import AuthenticationError
from backend.core.logging import get_logger
from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)

router = APIRouter(tags=["cts-live"])


@router.websocket("/ws/cts")
async def cts_live_websocket(websocket: WebSocket) -> None:
    """Accept a live-view WebSocket and relay CTS broadcasts."""
    client_ip = websocket.client.host if websocket.client else "unknown"
    logger.debug("cts_live_ws_connect_attempt", client=client_ip)

    if not settings.as_bool("cts.enabled"):
        logger.warning("cts_live_ws_rejected_disabled", client=client_ip)
        await websocket.close(code=1008, reason="cts.disabled")
        return

    raw_key = (
        websocket.headers.get("x-api-key")
        or websocket.headers.get("sec-websocket-protocol", "").strip()
    )
    if not raw_key:
        logger.warning("cts_live_ws_rejected_no_key", client=client_ip)
        await websocket.close(code=1008, reason="auth_required")
        return

    try:
        auth = _resolve_key(raw_key)
    except AuthenticationError:
        logger.warning("cts_live_ws_rejected_auth_failed", client=client_ip)
        await websocket.close(code=1008, reason="auth_failed")
        return

    if not has_permission(auth, "GET", "/ws/cts"):
        logger.warning(
            "cts_live_ws_rejected_permission_denied",
            client=client_ip,
            name=auth.name,
        )
        await websocket.close(code=1008, reason="permission_denied")
        return

    manager: ConnectionManager | None = websocket.app.state.ws_manager
    if manager is None:
        logger.error("cts_live_ws_rejected_no_manager", client=client_ip)
        await websocket.close(code=1011, reason="server_not_ready")
        return

    accepted = await manager.connect(websocket)
    if not accepted:
        logger.warning(
            "cts_live_ws_rejected_manager_full",
            client=client_ip,
        )
        return

    logger.info("cts_live_ws_connected", client=client_ip, name=auth.name)

    try:
        # Keep the connection open; incoming client messages are a no-op for
        # now (the client only needs to listen), but we still read to detect
        # disconnects promptly.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("cts_live_client_disconnected", subject=auth.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cts_live_ws_error", error=str(exc))
    finally:
        await manager.disconnect(websocket)
