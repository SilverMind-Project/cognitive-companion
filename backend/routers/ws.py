"""
WebSocket router - /ws/audio endpoint for real-time voice interaction.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/audio")
async def websocket_audio(websocket: WebSocket):
    """Bidirectional audio WebSocket endpoint.

    Accepts audio bytes and text commands from the client, forwards them
    to the configured realtime backend, and relays responses back.
    """
    from backend.integrations.llm.gemini_live import GeminiLiveProvider
    from backend.mcp.gemini_adapter import GeminiToolAdapter
    from backend.services.conversation_manager import ConversationManager
    from backend.websocket.audio_handler import AudioSessionHandler
    from backend.websocket.connection_manager import ConnectionManager

    # Pull shared objects from app.state
    app = websocket.app
    manager: ConnectionManager | None = app.state.ws_manager
    realtime_provider: GeminiLiveProvider | None = app.state.realtime_provider
    conversation_manager: ConversationManager | None = app.state.conversation_manager
    rag_lookup = getattr(app.state, "rag_lookup", None)  # Not yet wired in lifespan
    gemini_adapter: GeminiToolAdapter | None = app.state.gemini_adapter

    if manager is None:
        await websocket.close(code=1011, reason="Server not ready")
        return

    accepted = await manager.connect(websocket)
    if not accepted:
        return

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
    except Exception as exc:
        logger.error("ws_audio_handler_error", error=str(exc))
    finally:
        await manager.disconnect(websocket)
        logger.info("ws_audio_handler_exited")
