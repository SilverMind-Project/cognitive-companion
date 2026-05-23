"""
WebSocket connection manager - tracks active client connections, broadcasts
notifications, and manages a task queue for backend-initiated prompts.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket

from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and a backend prompt queue."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.prompt_queue: asyncio.Queue[tuple[str, Callable | None, float, str | None, dict[str, Any]]] = asyncio.Queue()
        self.max_connections: int = settings.as_int("websocket.max_connections")
        # Guards the active_connections list against concurrent connect /
        # disconnect / broadcast operations.  Without the lock, two simultaneous
        # upgrade requests could both pass the max-connections check before
        # either appends to the list because ``await websocket.accept()``
        # yields control between the check and the append.
        self._lock: asyncio.Lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> bool:
        """Accept and register a WebSocket connection.

        Returns False if the maximum number of connections has been reached.
        """
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                logger.warning("ws_max_connections_reached")
                await websocket.close(code=1013, reason="Max connections reached")
                return False

            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info("ws_client_connected", total=len(self.active_connections))
            return True

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                logger.info("ws_client_disconnected", total=len(self.active_connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast a JSON payload to all connected clients.

        Silently removes connections that have gone stale.
        """
        # The payload's own 'type' key (e.g. "warning", "emergency") is the
        # authoritative message type.  Fall back to "command" for payloads
        # that don't specify a type.
        message = {"type": "command", **payload}

        # Normalize alert payloads
        if (
            message.get("type") == "emergency_alert"
            and "alert_id" not in message
            and "id" in message
        ):
            message["alert_id"] = message["id"]

        # Take a snapshot of current connections so we don't hold the lock
        # while doing I/O.  Stale connections discovered during send are
        # removed in a second pass under the lock.
        async with self._lock:
            snapshot = list(self.active_connections)

        disconnected: list[WebSocket] = []
        for ws in snapshot:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning("ws_broadcast_send_error", error=str(exc))
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect(ws)

    async def broadcast_bytes(self, data: bytes) -> None:
        """Broadcast raw bytes to all connected clients.

        Used for streaming binary audio (e.g. PCM chunks for TTS announcements).
        Silently removes connections that have gone stale.
        """
        async with self._lock:
            snapshot = list(self.active_connections)

        disconnected: list[WebSocket] = []
        for ws in snapshot:
            try:
                await ws.send_bytes(data)
            except Exception as exc:
                logger.warning("ws_broadcast_bytes_error", error=str(exc))
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        """Send a JSON payload to a specific client."""
        try:
            await websocket.send_json(payload)
        except Exception:
            logger.warning("ws_send_to_error")
            await self.disconnect(websocket)

    async def send_backend_task(
        self,
        prompt: str,
        callback: Callable | None = None,
        ttl_seconds: int = 300,
        *,
        voice_instruction: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Enqueue a prompt for the realtime AI backend.

        The prompt will be picked up by the first active audio session.
        Expires after ``ttl_seconds`` if not consumed.

        Args:
            prompt: The text to send to Gemini Live.
            callback: Optional callback invoked on turn completion.
            ttl_seconds: Expiry for unconsumed prompts.
            voice_instruction: When non-empty, composed into the Gemini
                system instruction before sending. See the unified
                composition rule in VoiceInstructionConfig.compose().
            metadata: Structured dict with execution_id, step_id, etc.
                Replaces the ad-hoc [System context: ...] text annotation.
        """
        expiration = time.time() + ttl_seconds
        await self.prompt_queue.put(
            (prompt, callback, expiration, voice_instruction, metadata or {})
        )
        logger.info("ws_backend_task_queued", queue_size=self.prompt_queue.qsize())

    @property
    def has_connections(self) -> bool:
        return len(self.active_connections) > 0
