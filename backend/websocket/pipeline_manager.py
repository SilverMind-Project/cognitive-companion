"""Pipeline WebSocket connection manager.

A lightweight dedicated manager for the /ws/pipeline channel so pipeline
execution events are not mixed with audio client connections.  This follows
the same pattern as ConnectionManager but without the audio-specific
prompt_queue.  Only pipeline subscribers receive pipeline events.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from backend.core.logging import get_logger

logger = get_logger(__name__)

_MAX_PIPELINE_CONNECTIONS = 50


class PipelineConnectionManager:
    """Manages active /ws/pipeline connections and broadcasts events to them."""

    def __init__(self, max_connections: int = _MAX_PIPELINE_CONNECTIONS) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self.max_connections = max_connections

    async def connect(self, websocket: WebSocket) -> bool:
        """Accept and register the connection; returns False if limit reached."""
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                logger.warning("pipeline_ws_max_connections_reached")
                await websocket.close(code=1013, reason="Max connections reached")
                return False
            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info(
                "pipeline_ws_client_connected",
                total=len(self.active_connections),
            )
            return True

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister the connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                logger.info(
                    "pipeline_ws_client_disconnected",
                    total=len(self.active_connections),
                )

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Fan the payload to all subscribed pipeline clients."""
        async with self._lock:
            snapshot = list(self.active_connections)

        disconnected: list[WebSocket] = []
        for ws in snapshot:
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.warning("pipeline_ws_send_error", error=str(exc))
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect(ws)

    async def publish_event(self, event_dict: dict[str, Any]) -> None:
        """Publish a pipeline execution event to all connected clients."""
        await self.broadcast(event_dict)

    @property
    def has_connections(self) -> bool:
        return len(self.active_connections) > 0
