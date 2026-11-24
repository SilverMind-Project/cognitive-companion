"""
WebSocket router - /ws/audio endpoint for real-time voice interaction
and /ws/pipeline endpoint for live pipeline execution events.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from backend.core.auth import WS_ROUTE_TOKENS, authenticate_websocket, declare_tokens
from backend.core.logging import get_logger
from backend.schemas.companion_surface_ws import SurfacePlatform

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])

_AUDIO_TOKEN = WS_ROUTE_TOKENS["/ws/audio"]
_PIPELINE_EVENTS_TOKEN = WS_ROUTE_TOKENS["/ws/pipeline"]
declare_tokens(_AUDIO_TOKEN, _PIPELINE_EVENTS_TOKEN)


@router.websocket("/audio")
async def websocket_audio(
    websocket: WebSocket,
    surface_id: str | None = Query(default=None, min_length=1, max_length=128),
    platform: SurfacePlatform | None = Query(default=None),
) -> None:
    """Bidirectional audio WebSocket endpoint for companion surfaces.

    Accepts audio bytes and text commands from the client, forwards them
    to the configured realtime backend, and relays responses back. The
    socket carries resident prompts and opens microphones, so it requires
    a key holding ``companion.audio:act``. A client that names a registered,
    enabled ``surface_id`` receives that surface's room-targeted deliveries.
    Any other ``surface_id`` (a stale or mistyped kiosk setting, a disabled
    surface) connects as a surface-less screen and is logged: cutting a
    companion screen off entirely would be worse than losing its room routing.
    """
    from backend.integrations.llm.base import RealtimeLLMProvider
    from backend.mcp.gemini_adapter import GeminiToolAdapter
    from backend.services.companion_surface import CompanionSurfaceService
    from backend.services.conversation_manager import ConversationManager
    from backend.websocket.audio_handler import AudioSessionHandler
    from backend.websocket.connection_manager import ConnectionManager

    ws_auth = await authenticate_websocket(websocket, _AUDIO_TOKEN, channel="companion_audio")
    if ws_auth is None:
        return

    # Pull shared objects from app.state
    app = websocket.app
    manager: ConnectionManager | None = app.state.ws_manager
    realtime_provider: RealtimeLLMProvider | None = app.state.realtime_provider
    conversation_manager: ConversationManager | None = app.state.conversation_manager
    gemini_adapter: GeminiToolAdapter | None = app.state.gemini_adapter

    if manager is None:
        await websocket.close(code=1011, reason="Server not ready")
        return

    if surface_id is not None:
        surfaces: CompanionSurfaceService | None = app.state.companion_surface_service
        surface = (
            await run_in_threadpool(surfaces.get_surface, surface_id)
            if surfaces is not None
            else None
        )
        if surface is None or not surface.is_enabled:
            logger.warning("ws_audio_unknown_surface_unbound", surface_id=surface_id)
            surface_id = None

    accepted = await manager.connect(
        websocket, surface_id=surface_id, subprotocol=ws_auth.subprotocol
    )
    if not accepted:
        return
    logger.info(
        "ws_audio_connected", name=ws_auth.auth.name, surface_id=surface_id, platform=platform
    )
    guided_task_service = getattr(app.state, "guided_task_service", None)
    if guided_task_service is not None:
        try:
            await guided_task_service.on_session_opened()
        except Exception as exc:  # noqa: BLE001
            logger.warning("guided_session_open_hook_failed", error=str(exc))

    try:
        handler = AudioSessionHandler(
            websocket=websocket,
            manager=manager,
            realtime_provider=realtime_provider,
            conversation_manager=conversation_manager,
            tool_adapter=gemini_adapter,
            surface_id=surface_id,
        )
        await handler.run()
    except WebSocketDisconnect:
        logger.info("ws_audio_client_disconnected")
    except Exception as exc:  # noqa: BLE001
        logger.error("ws_audio_handler_error", error=str(exc))
    finally:
        await manager.disconnect(websocket)
        logger.info("ws_audio_handler_exited")


@router.websocket("/pipeline")
async def websocket_pipeline(websocket: WebSocket) -> None:
    """Read-only WebSocket that streams PipelineExecutionEvents to subscribers.

    Auth: API key via ``x-api-key`` header or ``sec-websocket-protocol``
    (same pattern as ``/ws/cts``).  Requires ``pipeline.events:read``.
    Closes with 1008 on auth failure.
    """
    from backend.websocket.pipeline_manager import PipelineConnectionManager

    client_ip = websocket.client.host if websocket.client else "unknown"
    ws_auth = await authenticate_websocket(websocket, _PIPELINE_EVENTS_TOKEN, channel="pipeline")
    if ws_auth is None:
        return
    auth = ws_auth.auth

    manager: PipelineConnectionManager | None = getattr(
        websocket.app.state, "pipeline_ws_manager", None
    )
    if manager is None:
        logger.error("pipeline_ws_rejected_no_manager", client=client_ip)
        await websocket.close(code=1011, reason="server_not_ready")
        return

    accepted = await manager.connect(websocket, subprotocol=ws_auth.subprotocol)
    if not accepted:
        return

    logger.info("pipeline_ws_connected", client=client_ip, name=auth.name)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("pipeline_ws_disconnected", name=auth.name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline_ws_error", error=str(exc))
    finally:
        await manager.disconnect(websocket)
