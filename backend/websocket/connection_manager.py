"""
WebSocket connection manager – tracks active client connections, broadcasts
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
        self.prompt_queue: asyncio.Queue = asyncio.Queue()
        self.max_connections: int = settings.get("websocket.max_connections", 10)

    async def connect(self, websocket: WebSocket) -> bool:
        """Accept and register a WebSocket connection.

        Returns False if the maximum number of connections has been reached.
        """
        if len(self.active_connections) >= self.max_connections:
            logger.warning("ws_max_connections_reached")
            await websocket.close(code=1013, reason="Max connections reached")
            return False

        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_client_connected", total=len(self.active_connections))
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("ws_client_disconnected", total=len(self.active_connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast a JSON payload to all connected clients.

        Silently removes connections that have gone stale.
        """
        disconnected: list[WebSocket] = []
        # The payload's own 'type' key (e.g. "warning", "emergency") is the
        # authoritative message type.  Fall back to "command" for payloads
        # that don't specify a type.
        message = {"type": "command", **payload}

        # Normalize alert payloads
        if message.get("type") == "emergency_alert" and "alert_id" not in message:
            if "id" in message:
                message["alert_id"] = message["id"]

        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning("ws_broadcast_send_error", error=str(exc))
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        """Send a JSON payload to a specific client."""
        try:
            await websocket.send_json(payload)
        except Exception:
            logger.warning("ws_send_to_error")
            self.disconnect(websocket)

    async def send_backend_task(
        self,
        prompt: str,
        callback: Callable | None = None,
        ttl_seconds: int = 300,
    ) -> None:
        """Enqueue a prompt for the realtime AI backend.

        The prompt will be picked up by the first active audio session.
        Expires after ``ttl_seconds`` if not consumed.
        """
        expiration = time.time() + ttl_seconds
        await self.prompt_queue.put((prompt, callback, expiration))
        logger.info("ws_backend_task_queued", queue_size=self.prompt_queue.qsize())

    @property
    def has_connections(self) -> bool:
        return len(self.active_connections) > 0
