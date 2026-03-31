"""
WebSocket audio handler - manages the bidirectional audio pipeline between
a client WebSocket and a realtime LLM backend (e.g. Gemini Live).

Key design points:
- The FastAPI server always accepts audio/text from connected clients.
- The connection to the realtime backend is lazy: opened only when there
  is actual audio or prompt activity, and re-established after each session
  ends. No keepalive messages are sent to the provider.
- Clients connected for notifications only (no audio activity) hold an
  open WebSocket without triggering a Gemini session, so push notifications
  are delivered without incurring any realtime API cost.
- Supports pluggable backends via RealtimeLLMProvider.
- Conversation history is preserved across backend reconnects.
- A continuous prompt-bridge task transfers orchestrator prompts from the
  connection manager queue into the per-session queue so that incoming
  prompts can wake an idle session.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

from fastapi import WebSocket, WebSocketDisconnect

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.llm.base import RealtimeLLMProvider
from backend.services.conversation_manager import ConversationManager
from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)

RETRY_DELAY = 2


class AudioSessionHandler:
    """Manages a single client's audio session lifecycle.

    Coordinates:
    - Receiving audio/text from the client
    - Forwarding to the realtime backend (lazily, on first activity)
    - Relaying backend responses (audio, transcripts) back to the client
    - Backend prompt queue processing
    - Conversation persistence
    """

    def __init__(
        self,
        websocket: WebSocket,
        manager: ConnectionManager,
        realtime_provider: RealtimeLLMProvider | None,
        conversation_manager: ConversationManager | None = None,
        rag_lookup: Callable[[str], str] | None = None,
    ) -> None:
        self.ws = websocket
        self.manager = manager
        self.provider = realtime_provider
        self.conv_manager = conversation_manager
        self.rag_lookup = rag_lookup

        # Internal queues and events
        self._client_to_backend: asyncio.Queue = asyncio.Queue()
        self._client_disconnected = asyncio.Event()

        # Conversation state (survives reconnects)
        self._conversation_log: list[dict[str, str]] = []
        self._pending_user_text: list[str] = []
        self._pending_assistant_text: list[str] = []
        self._pending_prompt_text: list[str] = []

        # Callback for backend-initiated (orchestrator) prompts
        self._current_callback: Callable | None = None
        self._current_callback_text: str = ""
        self._callback_task: asyncio.Task | None = None
        self._is_orchestrator_turn: bool = False

        # Conversation session ID
        self._session_id: int | None = None

        # Lazy connection flag
        self._backend_active = False

    async def run(self) -> None:
        """Main entry point - run until the client disconnects."""
        # Create conversation session
        if self.conv_manager:
            self._session_id = self.conv_manager.create_session()

        client_task = asyncio.create_task(
            self._receive_from_client(), name="ws-client-reader"
        )

        if self.provider and getattr(self.provider, "configured", True):
            backend_task = asyncio.create_task(
                self._run_backend_loop(), name="ws-backend-loop"
            )
        else:
            backend_task = asyncio.create_task(
                self._no_backend_fallback(), name="ws-no-backend"
            )

        await asyncio.gather(client_task, backend_task, return_exceptions=True)

        # Cleanup
        if self.conv_manager and self._session_id:
            self.conv_manager.end_session(self._session_id)

    # ------------------------------------------------------------------
    # Client reader
    # ------------------------------------------------------------------

    async def _receive_from_client(self) -> None:
        """Permanently reads from the client WebSocket."""
        try:
            while True:
                msg = await self.ws.receive()
                if "bytes" in msg:
                    await self._client_to_backend.put(("audio", msg["bytes"]))
                elif "text" in msg:
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    msg_type = data.get("type", "")
                    if msg_type == "end_of_turn":
                        await self._client_to_backend.put(("end_of_turn", None))
                    elif msg_type == "text":
                        text = data.get("text", "")
                        if text and self.rag_lookup:
                            # Enrich with RAG context
                            context = self.rag_lookup(text)
                            if context:
                                text = f"[Context: {context}]\n{text}"
                        await self._client_to_backend.put(("text", text))
        except WebSocketDisconnect:
            logger.info("ws_client_disconnected_in_reader")
        except Exception as exc:
            logger.error("ws_client_reader_error", error=str(exc))
        finally:
            self._client_disconnected.set()

    # ------------------------------------------------------------------
    # Backend loop (with reconnection)
    # ------------------------------------------------------------------

    async def _run_backend_loop(self) -> None:
        """Connects (and reconnects) to the realtime backend until the client leaves.

        A Gemini session is opened only when incoming data is present (audio,
        text, or an orchestrator prompt). After each session ends the loop
        waits for new activity before reconnecting. No keepalive messages are
        sent; idle sessions are allowed to expire naturally.
        """
        # Bridge orchestrator prompts from the connection-manager queue into
        # _client_to_backend continuously, so that prompt arrivals can wake
        # _wait_for_activity() even before a session is open.
        async def _bridge_prompts() -> None:
            while True:
                prompt, callback, exp = await self.manager.prompt_queue.get()
                await self._client_to_backend.put(("prompt", (prompt, callback, exp)))
                self.manager.prompt_queue.task_done()

        bridge = asyncio.create_task(_bridge_prompts(), name="prompt-bridge")
        try:
            while not self._client_disconnected.is_set():
                # Wait for incoming audio/text/prompt before opening a session.
                await self._wait_for_activity()
                if self._client_disconnected.is_set():
                    return

                try:
                    config = self.provider.build_config(
                        conversation_history=self._get_history_text()
                    )
                    session = await self.provider.connect(config)
                    self._backend_active = True

                    await self.ws.send_json(
                        {"type": "status", "message": "backend_connected"}
                    )
                    logger.info("ws_backend_connected")

                    async def forward_to_backend(session=session) -> None:
                        while True:
                            kind, payload = await self._client_to_backend.get()

                            if kind == "audio":
                                await self.provider.send_audio(session, payload)
                            elif kind == "end_of_turn":
                                pass  # Provider handles turn detection
                            elif kind == "text":
                                await self.provider.send_text(session, payload)
                            elif kind == "prompt":
                                text, callback, exp = payload
                                if time.time() > exp:
                                    logger.debug("ws_backend_prompt_expired")
                                    continue
                                self._current_callback = callback
                                self._is_orchestrator_turn = True
                                self._pending_prompt_text.append(text)
                                await self.provider.send_text(session, text)

                    async def receive_from_backend(session=session) -> None:
                        async for response in self.provider.receive(session):
                            await self._handle_backend_response(response)

                    tasks = [
                        asyncio.create_task(forward_to_backend(), name="forward"),
                        asyncio.create_task(receive_from_backend(), name="receive"),
                        asyncio.create_task(
                            self._client_disconnected.wait(), name="client-gone"
                        ),
                    ]

                    _done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    await self.provider.disconnect(session)
                    self._backend_active = False

                    if self._client_disconnected.is_set():
                        return

                    logger.info(
                        "ws_backend_session_ended",
                        turns=len(self._conversation_log),
                    )
                    await self.ws.send_json(
                        {"type": "status", "message": "backend_reconnecting"}
                    )

                except Exception as exc:
                    self._backend_active = False
                    if self._client_disconnected.is_set():
                        return
                    logger.error("ws_backend_error", error=str(exc))
                    await self.ws.send_json(
                        {"type": "status", "message": "backend_reconnecting"}
                    )
                    await asyncio.sleep(RETRY_DELAY)
        finally:
            bridge.cancel()

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    async def _handle_backend_response(self, response) -> None:
        """Process a response from the Gemini Live backend."""
        server_content = getattr(response, "server_content", None)
        if server_content is None:
            return

        model_turn = getattr(server_content, "model_turn", None)
        if model_turn and model_turn.parts:
            for part in model_turn.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    await self.ws.send_bytes(part.inline_data.data)

        # Output transcription
        output_tx = getattr(server_content, "output_transcription", None)
        if output_tx and output_tx.text:
            self._pending_assistant_text.append(output_tx.text)
            self._current_callback_text += output_tx.text

        # Input transcription
        input_tx = getattr(server_content, "input_transcription", None)
        if input_tx and input_tx.text:
            self._pending_user_text.append(input_tx.text)

        # Turn complete
        if getattr(server_content, "turn_complete", False):
            is_orchestrator = self._is_orchestrator_turn
            prompt_text = "".join(self._pending_prompt_text).strip()
            user_text = "".join(self._pending_user_text).strip()
            assistant_text = "".join(self._pending_assistant_text).strip()

            # Commit to conversation log (all actors, for context continuity)
            self._conversation_log.append({
                "user": user_text,
                "assistant": assistant_text,
                **({"orchestrator": prompt_text} if is_orchestrator else {}),
            })

            # Persist to DB
            if self.conv_manager and self._session_id:
                if is_orchestrator and prompt_text:
                    self.conv_manager.add_turn(
                        self._session_id, "orchestrator", prompt_text
                    )
                elif user_text:
                    self.conv_manager.add_turn(self._session_id, "user", user_text)
                if assistant_text:
                    self.conv_manager.add_turn(
                        self._session_id, "assistant", assistant_text
                    )

            # Send transcripts to client.
            # Orchestrator prompts are never shown to the senior — they are
            # internal nudges from the Cognitive Companion system.  The agent's
            # response to an orchestrator prompt is tagged "assistant" so the
            # senior can still hear/see the AI speaking, but the *trigger* that
            # caused the AI to speak remains hidden.
            if is_orchestrator:
                # Don't send the orchestrator prompt text to the UI.
                # The agent's spoken response is still delivered as audio
                # and shown as an assistant transcript.
                if assistant_text:
                    await self.ws.send_json({
                        "type": "transcript",
                        "source": "assistant",
                        "text": assistant_text,
                    })
            else:
                if user_text:
                    await self.ws.send_json({
                        "type": "transcript",
                        "source": "user",
                        "text": user_text,
                    })
                if assistant_text:
                    await self.ws.send_json({
                        "type": "transcript",
                        "source": "assistant",
                        "text": assistant_text,
                    })

            # Execute callback if pending
            if self._current_callback is not None:
                try:
                    self._callback_task = asyncio.create_task(
                        self._current_callback(self._current_callback_text),
                        name="ws-callback",
                    )
                except Exception:
                    logger.exception("ws_callback_error")
                self._current_callback = None
                self._current_callback_text = ""

            # Reset buffers
            self._pending_user_text.clear()
            self._pending_assistant_text.clear()
            self._pending_prompt_text.clear()
            self._is_orchestrator_turn = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_history_text(self) -> str:
        """Build a text summary of recent conversation for context injection."""
        lines: list[str] = []
        for turn in self._conversation_log[-40:]:
            if turn.get("user"):
                lines.append(f"User: {turn['user']}")
            if turn.get("assistant"):
                lines.append(f"Assistant: {turn['assistant']}")
        return "\n".join(lines)

    async def _wait_for_activity(self) -> None:
        """Block until the first audio/text/prompt arrives or the client disconnects."""
        while not self._client_disconnected.is_set():
            try:
                item = await asyncio.wait_for(
                    self._client_to_backend.get(), timeout=1.0
                )
                # Put it back so the forward loop can consume it
                await self._client_to_backend.put(item)
                return
            except TimeoutError:
                continue

    async def _no_backend_fallback(self) -> None:
        """Keep the WebSocket alive for push notifications when no AI backend."""
        await self.ws.send_json(
            {"type": "error", "message": "Backend AI not configured."}
        )
        await self._client_disconnected.wait()
