"""
WebSocket router - /ws/audio endpoint for real-time voice interaction.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/audio")
async def websocket_audio(websocket: WebSocket, request: Request | None = None):
    """Bidirectional audio WebSocket endpoint.

    Accepts audio bytes and text commands from the client, forwards them
    to the configured realtime backend, and relays responses back.
    """
    from backend.websocket.audio_handler import AudioSessionHandler

    # Pull shared objects from app.state
    app = websocket.app
    manager = getattr(app.state, "ws_manager", None)
    realtime_provider = getattr(app.state, "realtime_provider", None)
    conversation_manager = getattr(app.state, "conversation_manager", None)
    rag_lookup = getattr(app.state, "rag_lookup", None)
    gemini_adapter = getattr(app.state, "gemini_adapter", None)

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
