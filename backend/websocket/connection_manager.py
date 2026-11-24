"""
WebSocket connection manager - tracks active client connections, broadcasts
notifications, and routes backend-initiated prompts to companion surfaces.

A connection may belong to a registered companion surface (one tablet, speaker,
display, or TV). Room-specific deliveries go to that surface only; a connection
with no surface, or a delivery with no target, keeps the house-wide behaviour.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import WebSocket

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.schemas.companion_surface_ws import SurfaceAttentionStateIn, SurfaceHardwareCommand

logger = get_logger(__name__)

# A queued realtime prompt: its text, turn-complete callback, expiry (epoch
# seconds), system instruction, and routing metadata.
PromptItem = tuple[str, Callable | None, float, str | None, dict[str, Any]]


class CompanionAudioSession(Protocol):
    """A live ``/ws/audio`` session the manager can route prompts and releases to."""

    @property
    def conversation_session_id(self) -> int | None: ...

    async def release_voice_instruction(self, owner: str) -> bool: ...

    def enqueue_prompt(self, item: PromptItem) -> None: ...


@dataclass(frozen=True)
class SurfaceAttention:
    """The latest attention reading a surface reported, stamped on arrival."""

    face_present: bool
    head_yaw_deg: float | None
    head_pitch_deg: float | None
    received_at: datetime


class ConnectionManager:
    """Manages active WebSocket connections, surface routing, and the prompt queue."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        # Prompts with no target surface. Every live audio session drains it, so an
        # untargeted prompt is spoken by whichever session takes it first.
        self.prompt_queue: asyncio.Queue[PromptItem] = asyncio.Queue()
        self.max_connections: int = settings.as_int("websocket.max_connections")
        # Guards the active_connections list against concurrent connect /
        # disconnect / broadcast operations.  Without the lock, two simultaneous
        # upgrade requests could both pass the max-connections check before
        # either appends to the list because ``await websocket.accept``
        # yields control between the check and the append.
        self._lock: asyncio.Lock = asyncio.Lock()
        # The surface each connection authenticated as. A surface may hold more than
        # one socket for a moment (a reconnect overlapping the old socket's close).
        self._surface_of: dict[WebSocket, str] = {}
        # Every live /ws/audio session, in registration order, with its surface. A
        # delivery's instruction is applied by whichever session consumed its prompt,
        # so a release must reach all of them.
        self._audio_handlers: dict[CompanionAudioSession, str | None] = {}
        self._attention: dict[str, SurfaceAttention] = {}

    async def connect(
        self,
        websocket: WebSocket,
        *,
        surface_id: str | None = None,
        subprotocol: str | None = None,
    ) -> bool:
        """Accept and register a WebSocket connection.

        ``subprotocol`` is echoed in the handshake when the client authenticated
        through ``Sec-WebSocket-Protocol``: a browser drops a connection whose
        requested subprotocol the server does not select. Returns False if the
        maximum number of connections has been reached.
        """
        async with self._lock:
            if len(self.active_connections) >= self.max_connections:
                logger.warning("ws_max_connections_reached")
                await websocket.close(code=1013, reason="Max connections reached")
                return False

            await websocket.accept(subprotocol=subprotocol)
            self.active_connections.append(websocket)
            if surface_id is not None:
                self._surface_of[websocket] = surface_id
            logger.info(
                "ws_client_connected",
                total=len(self.active_connections),
                surface_id=surface_id,
            )
            return True

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                surface_id = self._surface_of.pop(websocket, None)
                if surface_id is not None and not self.is_surface_connected(surface_id):
                    self._attention.pop(surface_id, None)
                logger.info(
                    "ws_client_disconnected",
                    total=len(self.active_connections),
                    surface_id=surface_id,
                )

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Broadcast a JSON payload to all connected clients.

        Silently removes connections that have gone stale.
        """
        async with self._lock:
            snapshot = list(self.active_connections)
        await self._send_json_to(snapshot, self._as_message(payload))

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

    # ------------------------------------------------------------------
    # Surface routing
    # ------------------------------------------------------------------

    def is_surface_connected(self, surface_id: str) -> bool:
        """Whether at least one live connection belongs to ``surface_id``."""
        return surface_id in self._surface_of.values()

    def reaches_surface(self, surface_id: str | None) -> bool:
        """Whether a delivery aimed at ``surface_id`` would reach a companion screen.

        True when that surface is connected, or when it is not (or no surface was
        chosen) and any companion connection is open, because resident-safe content
        then falls back to every companion connection.
        """
        if surface_id is not None and self.is_surface_connected(surface_id):
            return True
        return self.has_connections

    async def send_to_surface(self, surface_id: str | None, payload: dict[str, Any]) -> int:
        """Send resident-safe content to one surface, or to every connection.

        Goes only to ``surface_id``'s connections when it has any; otherwise to every
        connection, so a delivery whose surface is offline still reaches her on
        another screen. Never use this for anything that opens a microphone or
        camera without a prompt to answer: use :meth:`send_hardware_command`.
        Returns the number of connections it was sent to.
        """
        async with self._lock:
            targets = (
                [ws for ws, sid in self._surface_of.items() if sid == surface_id]
                if surface_id is not None
                else []
            )
            if not targets:
                targets = list(self.active_connections)
        return await self._send_json_to(targets, self._as_message(payload))

    async def send_hardware_command(self, command: SurfaceHardwareCommand) -> int:
        """Send a wake/capture command to its surface only, never as a broadcast.

        Waking a screen or opening a microphone in a room she is not in is a privacy
        failure, so an offline target means the command is dropped (and logged), not
        rerouted. Returns the number of connections it reached.
        """
        async with self._lock:
            targets = [ws for ws, sid in self._surface_of.items() if sid == command.surface_id]
        if not targets:
            logger.info(
                "surface_hardware_command_undelivered",
                surface_id=command.surface_id,
                reason=command.reason,
                captures=command.captures,
            )
            return 0
        sent = await self._send_json_to(targets, command.model_dump(mode="json"))
        logger.info(
            "surface_hardware_command_sent",
            surface_id=command.surface_id,
            reason=command.reason,
            enable_microphone=command.enable_microphone,
            enable_camera=command.enable_camera,
            lease_seconds=command.lease_seconds,
        )
        return sent

    def record_attention(self, surface_id: str, reading: SurfaceAttentionStateIn) -> None:
        """Keep a connected surface's latest attention reading (in memory only)."""
        self._attention[surface_id] = SurfaceAttention(
            face_present=reading.face_present,
            head_yaw_deg=reading.head_yaw_deg,
            head_pitch_deg=reading.head_pitch_deg,
            received_at=datetime.now(UTC),
        )

    def latest_attention(self, surface_id: str) -> SurfaceAttention | None:
        """The latest attention reading from a connected surface, if any."""
        return self._attention.get(surface_id)

    # ------------------------------------------------------------------
    # Realtime prompts and audio sessions
    # ------------------------------------------------------------------

    async def send_backend_task(
        self,
        prompt: str,
        callback: Callable | None = None,
        ttl_seconds: int = 300,
        *,
        voice_instruction: str | None = None,
        metadata: dict[str, Any] | None = None,
        surface_id: str | None = None,
    ) -> None:
        """Queue a prompt for the realtime AI backend.

        With ``surface_id`` and a live audio session on that surface, the prompt goes
        to that session alone. Otherwise it joins the shared queue, which the first
        free audio session takes. Expires after ``ttl_seconds`` if not consumed.

        Args:
            prompt: The text to send to Gemini Live.
            callback: Optional callback invoked on turn completion.
            ttl_seconds: Expiry for unconsumed prompts.
            voice_instruction: When non-empty, composed into the Gemini
                system instruction before sending. See the unified
                composition rule in VoiceInstructionConfig.compose().
            metadata: Structured dict with execution_id, step_id, etc.
                Replaces the ad-hoc [System context: ...] text annotation.
            surface_id: The companion surface in the resident's room, if known.
        """
        item: PromptItem = (
            prompt,
            callback,
            time.time() + ttl_seconds,
            voice_instruction,
            metadata or {},
        )
        handler = self._handler_for(surface_id)
        if handler is not None:
            handler.enqueue_prompt(item)
            logger.info("ws_backend_task_routed", surface_id=surface_id)
            return
        await self.prompt_queue.put(item)
        logger.info(
            "ws_backend_task_queued",
            queue_size=self.prompt_queue.qsize(),
            surface_id=surface_id,
        )

    def register_audio_handler(
        self, handler: CompanionAudioSession, *, surface_id: str | None = None
    ) -> None:
        """Track a live audio session (and its surface) for routing and releases."""
        self._audio_handlers.pop(handler, None)
        self._audio_handlers[handler] = surface_id

    def unregister_audio_handler(self, handler: CompanionAudioSession) -> None:
        """Stop tracking an audio session that has ended."""
        self._audio_handlers.pop(handler, None)

    def conversation_session_id(self, surface_id: str | None = None) -> int | None:
        """The conversation of the audio session that would speak to ``surface_id``.

        The surface's own session when it has one, else the most recently opened
        session that has a conversation (the one an untargeted prompt is most
        likely to reach in a single-tablet home).
        """
        handler = self._handler_for(surface_id)
        if handler is not None and handler.conversation_session_id is not None:
            return handler.conversation_session_id
        for candidate in reversed(list(self._audio_handlers)):
            if candidate.conversation_session_id is not None:
                return candidate.conversation_session_id
        return None

    async def release_voice_instruction(self, owner: str) -> bool:
        """Restore the base persona on any session whose instruction ``owner`` set.

        Called when a quiz ends, an info card is dismissed, or a guided session reaches a
        terminal state, so the delivery's instruction does not outlive it. Returns
        whether any session held it.
        """
        released = False
        for handler in list(self._audio_handlers):
            try:
                released = await handler.release_voice_instruction(owner) or released
            except Exception:
                logger.exception("ws_voice_instruction_release_failed")
        return released

    @property
    def has_connections(self) -> bool:
        return len(self.active_connections) > 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _handler_for(self, surface_id: str | None) -> CompanionAudioSession | None:
        """The newest audio session on ``surface_id``, or None."""
        if surface_id is None:
            return None
        for handler, handler_surface in reversed(list(self._audio_handlers.items())):
            if handler_surface == surface_id:
                return handler
        return None

    @staticmethod
    def _as_message(payload: dict[str, Any]) -> dict[str, Any]:
        # The payload's own 'type' key (e.g. "warning", "emergency") is the
        # authoritative message type.  Fall back to "command" for payloads
        # that don't specify a type.
        message = {"type": "command", **payload}
        if (
            message.get("type") == "emergency_alert"
            and "alert_id" not in message
            and "id" in message
        ):
            message["alert_id"] = message["id"]
        return message

    async def _send_json_to(self, targets: list[WebSocket], message: dict[str, Any]) -> int:
        """Send ``message`` to ``targets``, dropping any that have gone stale."""
        disconnected: list[WebSocket] = []
        sent = 0
        for ws in targets:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as exc:
                logger.warning("ws_broadcast_send_error", error=str(exc))
                disconnected.append(ws)
        for ws in disconnected:
            await self.disconnect(ws)
        return sent
