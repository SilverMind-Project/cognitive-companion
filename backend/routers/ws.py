"""
WebSocket router - /ws/audio endpoint for real-time voice interaction
and /ws/pipeline endpoint for live pipeline execution events.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.auth import _resolve_key, has_permission
from backend.core.exceptions import AuthenticationError
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/audio")
async def websocket_audio(websocket: WebSocket):
    """Bidirectional audio WebSocket endpoint.

    Accepts audio bytes and text commands from the client, forwards them
    to the configured realtime backend, and relays responses back.
    """
    from backend.integrations.llm.base import RealtimeLLMProvider
    from backend.mcp.gemini_adapter import GeminiToolAdapter
    from backend.services.conversation_manager import ConversationManager
    from backend.websocket.audio_handler import AudioSessionHandler
    from backend.websocket.connection_manager import ConnectionManager

    # Pull shared objects from app.state
    app = websocket.app
    manager: ConnectionManager | None = app.state.ws_manager
    realtime_provider: RealtimeLLMProvider | None = app.state.realtime_provider
    conversation_manager: ConversationManager | None = app.state.conversation_manager
    rag_lookup = getattr(app.state, "rag_lookup", None)  # Not yet wired in lifespan
    gemini_adapter: GeminiToolAdapter | None = app.state.gemini_adapter

    if manager is None:
        await websocket.close(code=1011, reason="Server not ready")
        return

    accepted = await manager.connect(websocket)
    if not accepted:
        return
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
            rag_lookup=rag_lookup,
            tool_adapter=gemini_adapter,
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
    (same pattern as ``/ws/cts``).  Requires the ``pipeline.stream``
    permission entry in auth.yaml.  Closes with 1008 on auth failure.
    """
    from backend.websocket.pipeline_manager import PipelineConnectionManager

    client_ip = websocket.client.host if websocket.client else "unknown"

    raw_key = (
        websocket.headers.get("x-api-key")
        or websocket.headers.get("sec-websocket-protocol", "").strip()
    )
    if not raw_key:
        logger.warning("pipeline_ws_rejected_no_key", client=client_ip)
        await websocket.close(code=1008, reason="auth_required")
        return

    try:
        auth = _resolve_key(raw_key)
    except AuthenticationError:
        logger.warning("pipeline_ws_rejected_auth_failed", client=client_ip)
        await websocket.close(code=1008, reason="auth_failed")
        return

    if not has_permission(auth, "GET", "/ws/pipeline"):
        logger.warning(
            "pipeline_ws_rejected_permission_denied",
            client=client_ip,
            name=auth.name,
        )
        await websocket.close(code=1008, reason="permission_denied")
        return

    manager: PipelineConnectionManager | None = getattr(
        websocket.app.state, "pipeline_ws_manager", None
    )
    if manager is None:
        logger.error("pipeline_ws_rejected_no_manager", client=client_ip)
        await websocket.close(code=1011, reason="server_not_ready")
        return

    accepted = await manager.connect(websocket)
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
