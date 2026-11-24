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
  connection manager's shared queue into the per-session queue so that
  incoming prompts can wake an idle session. A prompt aimed at this session's
  companion surface is put on the per-session queue directly
  (``enqueue_prompt``), so it is never spoken in another room.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.core.exceptions import NotFoundError
from backend.core.logging import get_logger
from backend.integrations.llm.base import RealtimeLLMProvider, RealtimeSession
from backend.schemas.companion_surface_ws import SurfaceAttentionStateIn
from backend.schemas.guided_task_ws import GuidedStepActionIn, GuidedStepActionResultEvent
from backend.schemas.interactive_response import InteractiveResponseMessage
from backend.services.conversation_manager import ConversationManager
from backend.services.interactive_response import InteractiveResponseService
from backend.services.interactive_session.tagging import prefix_for_delivery, voice_owner_for
from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
from backend.websocket.connection_manager import ConnectionManager, PromptItem

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
        tool_adapter=None,
        *,
        surface_id: str | None = None,
    ) -> None:
        self.ws = websocket
        # The companion surface this socket authenticated as (None for a surface-less
        # connection, which only receives house-wide deliveries).
        self.surface_id = surface_id
        self.manager = manager
        self.provider = realtime_provider
        self.conv_manager = conversation_manager
        self.tool_adapter = tool_adapter

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

        # The conversation_sessions row this socket's turns go to. Created on first
        # activity (see ensure_conversation_session), never on connect: an idle screen
        # reconnecting must not leave an empty conversation behind each time.
        self._session_id: int | None = None

        # Lazy connection flag
        self._backend_active = False

        # Active session reference (for tool response sending)
        self._current_session: RealtimeSession | None = None

        # The system instruction the next realtime session must use (None means the
        # provider's base persona) and the delivery that set it. Only that delivery may
        # release it, so a card timing out never strips a running quiz's instruction.
        self._current_voice_instruction: str | None = None
        self._voice_instruction_owner: str | None = None

        # Items taken off the backend queue that must be processed again by the next
        # realtime session (a prompt that arrived with a new system instruction).
        self._replay: deque[tuple[str, Any]] = deque()

        # True from the first model output or tool call of a turn until turn_complete,
        # so an instruction release never cuts the companion off mid-sentence.
        self._model_turn_active = False
        self._sync_after_turn = False
        # Prompts that would change the instruction while a turn is still being spoken
        # (and any prompt queued behind them, to keep order). They wait for
        # turn_complete; ending the session at once would cut off what is being said.
        self._held_prompts: deque[tuple[str, Any]] = deque()

    async def run(self) -> None:
        """Main entry point - run until the client disconnects."""
        self.manager.register_audio_handler(self, surface_id=self.surface_id)

        # Best-effort: a freshly opened realtime session may satisfy a guided-task
        # session that is summoning the resident to a companion surface. Re-check
        # immediately so "she walks up and it starts" feels instant; the scheduled
        # recheck remains the robust fallback. Fire-and-forget so it never blocks the
        # audio loop.
        guided_task_service = getattr(self.ws.app.state, "guided_task_service", None)
        if guided_task_service is not None:
            asyncio.create_task(  # noqa: RUF006
                guided_task_service.on_session_opened(),
                name="guided-on-session-opened",
            )

        client_task = asyncio.create_task(self._receive_from_client(), name="ws-client-reader")

        if self.provider and getattr(self.provider, "configured", True):
            backend_task = asyncio.create_task(self._run_backend_loop(), name="ws-backend-loop")
        else:
            backend_task = asyncio.create_task(self._no_backend_fallback(), name="ws-no-backend")

        await asyncio.gather(client_task, backend_task, return_exceptions=True)

        # Cleanup
        self.manager.unregister_audio_handler(self)
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
                # receive() returns the raw ASGI message, so a client closing arrives as
                # a message rather than an exception; reading again after it raises.
                if msg.get("type") == "websocket.disconnect":
                    logger.info("ws_client_disconnected_in_reader", code=msg.get("code"))
                    return
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
                        await self._client_to_backend.put(("text", data.get("text", "")))
                    elif msg_type == "interactive_response":
                        await self._handle_interactive_response(data)
                    elif msg_type == "quiz_answer":
                        await self._handle_quiz_answer(data)
                    elif msg_type == "info_card_dismiss":
                        await self._handle_info_card_event(data)
                    elif msg_type == "guided_step_action":
                        await self._handle_guided_step_action(data)
                    elif msg_type == "surface_attention_state":
                        self._handle_surface_attention(data)
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
        if self.provider is None:
            return

        # Bridge orchestrator prompts from the connection-manager queue into
        # _client_to_backend continuously, so that prompt arrivals can wake
        # _wait_for_activity even before a session is open.
        async def _bridge_prompts() -> None:
            while True:
                item = await self.manager.prompt_queue.get()
                # Backwards-compatible unpack: 3-tuple (old) or 5-tuple (new)
                if len(item) == 3:
                    prompt, callback, exp = item
                    voice_instruction = None
                    metadata = {}
                else:
                    prompt, callback, exp, voice_instruction, metadata = item
                await self._client_to_backend.put(
                    ("prompt", (prompt, callback, exp, voice_instruction, metadata))
                )
                self.manager.prompt_queue.task_done()

        bridge = asyncio.create_task(_bridge_prompts(), name="prompt-bridge")
        try:
            while not self._client_disconnected.is_set():
                # Wait for incoming audio/text/prompt before opening a session.
                await self._wait_for_activity()
                if self._client_disconnected.is_set():
                    return

                try:
                    tool_declarations = None
                    if self.tool_adapter:
                        tool_declarations = self.tool_adapter.get_declarations()
                    session_instruction = self._current_voice_instruction
                    config = self.provider.build_config(
                        system_instruction=session_instruction or "",
                        conversation_history=self._get_history_text(),
                        tools=tool_declarations,
                    )
                    session = await self.provider.connect(config)
                    self._current_session = session
                    self._backend_active = True

                    await self.ws.send_json({"type": "status", "message": "backend_connected"})
                    logger.info("ws_backend_connected")

                    provider = self.provider

                    async def forward_to_backend(
                        session=session,
                        provider=provider,
                        session_instruction=session_instruction,
                    ) -> None:
                        # Returning ends this realtime session; the outer loop opens the
                        # next one with the current instruction and replays any held item.
                        # The session is never swapped in place: the receiver is bound to
                        # it and would keep reading a closed session.
                        while True:
                            kind, payload = await self._next_backend_item()

                            if kind == "audio":
                                await provider.send_audio(session, payload)
                            elif kind == "end_of_turn":
                                pass  # Provider handles turn detection
                            elif kind == "text":
                                await provider.send_text(session, payload)
                            elif kind == "wake":
                                pass  # A turn finished; held prompts are now replayed.
                            elif kind == "sync_instruction":
                                if self._current_voice_instruction != session_instruction:
                                    logger.info("ws_voice_instruction_released")
                                    return
                            elif kind == "prompt":
                                text, callback, exp, voice_instruction, metadata = payload
                                if time.time() > exp:
                                    logger.debug("ws_backend_prompt_expired")
                                    continue

                                changes_instruction = bool(
                                    voice_instruction and voice_instruction != session_instruction
                                )
                                if self._held_prompts or (
                                    changes_instruction and self._turn_in_progress()
                                ):
                                    self._held_prompts.append((kind, payload))
                                    logger.info("ws_prompt_held_until_turn_complete")
                                    continue
                                self._adopt_prompt_instruction(payload)
                                if changes_instruction:
                                    self._replay.append((kind, payload))
                                    logger.info("ws_voice_instruction_changed")
                                    return

                                prefix = prefix_for_delivery(metadata)
                                if prefix:
                                    text = f"{prefix} {text}"
                                self._current_callback = callback
                                self._is_orchestrator_turn = True
                                self._pending_prompt_text.append(text)
                                await provider.send_text(session, text)

                    async def receive_from_backend(session=session, provider=provider) -> None:
                        async for response in provider.receive(session):
                            await self._handle_backend_response(response)

                    tasks = [
                        asyncio.create_task(forward_to_backend(), name="forward"),
                        asyncio.create_task(receive_from_backend(), name="receive"),
                        asyncio.create_task(self._client_disconnected.wait(), name="client-gone"),
                    ]

                    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    await self.provider.disconnect(session)
                    self._backend_active = False
                    self._reset_turn_state()

                    if self._client_disconnected.is_set():
                        return

                    logger.info(
                        "ws_backend_session_ended",
                        turns=len(self._conversation_log),
                    )
                    await self.ws.send_json({"type": "status", "message": "backend_reconnecting"})

                except Exception as exc:
                    self._backend_active = False
                    self._reset_turn_state()
                    if self._client_disconnected.is_set():
                        return
                    logger.error("ws_backend_error", error=str(exc))
                    await self.ws.send_json({"type": "status", "message": "backend_reconnecting"})
                    await asyncio.sleep(RETRY_DELAY)
        finally:
            bridge.cancel()

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------

    async def _handle_backend_response(self, response) -> None:
        """Process a response from the Gemini Live backend."""
        self._model_turn_active = True
        # Handle tool calls (Gemini function calling)
        tool_call = getattr(response, "tool_call", None)
        if tool_call and tool_call.function_calls and self.tool_adapter:
            await self._handle_tool_calls(tool_call.function_calls)
            return

        # Handle tool call cancellations
        tool_call_cancellation = getattr(response, "tool_call_cancellation", None)
        if tool_call_cancellation:
            logger.info("gemini_tool_call_cancelled", ids=tool_call_cancellation.ids)
            return

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
            self._model_turn_active = False
            if self._sync_after_turn:
                self._sync_after_turn = False
                await self._client_to_backend.put(("sync_instruction", None))
            is_orchestrator = self._is_orchestrator_turn
            prompt_text = "".join(self._pending_prompt_text).strip()
            user_text = "".join(self._pending_user_text).strip()
            assistant_text = "".join(self._pending_assistant_text).strip()

            # Commit to conversation log (all actors, for context continuity)
            self._conversation_log.append(
                {
                    "user": user_text,
                    "assistant": assistant_text,
                    **({"orchestrator": prompt_text} if is_orchestrator else {}),
                }
            )

            # Persist to DB
            has_turn = (is_orchestrator and prompt_text) or user_text or assistant_text
            if self.conv_manager and has_turn:
                session_id = self.ensure_conversation_session()
                if session_id is not None:
                    if is_orchestrator and prompt_text:
                        self.conv_manager.add_turn(session_id, "orchestrator", prompt_text)
                    elif user_text:
                        self.conv_manager.add_turn(session_id, "user", user_text)
                    if assistant_text:
                        self.conv_manager.add_turn(session_id, "assistant", assistant_text)

            # Send transcripts to client.
            # Orchestrator prompts are never shown to the senior  they are
            # internal nudges from the Cognitive Companion system.  The agent's
            # response to an orchestrator prompt is tagged "assistant" so the
            # senior can still hear/see the AI speaking, but the *trigger* that
            # caused the AI to speak remains hidden.
            if is_orchestrator:
                # Don't send the orchestrator prompt text to the UI.
                # The agent's spoken response is still delivered as audio
                # and shown as an assistant transcript.
                if assistant_text:
                    await self.ws.send_json(
                        {
                            "type": "transcript",
                            "source": "assistant",
                            "text": assistant_text,
                        }
                    )
            else:
                if user_text:
                    await self.ws.send_json(
                        {
                            "type": "transcript",
                            "source": "user",
                            "text": user_text,
                        }
                    )
                if assistant_text:
                    await self.ws.send_json(
                        {
                            "type": "transcript",
                            "source": "assistant",
                            "text": assistant_text,
                        }
                    )

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
            if self._held_prompts:
                self._release_held_prompts()
                # Wake the forward loop, which may be blocked on the empty queue.
                await self._client_to_backend.put(("wake", None))

    # ------------------------------------------------------------------
    # Tool call handling
    # ------------------------------------------------------------------

    async def _handle_tool_calls(self, function_calls) -> None:
        """Execute provider tool calls and send responses back.

        Realtime providers may use synchronous function calling: audio generation
        pauses until tool responses are sent back. Tool results flow through
        spoken audio, never raw to the client.
        """
        responses = []
        tool_names = []
        for fc in function_calls:
            logger.info(
                "realtime_tool_call_executing",
                tool=fc.name,
                call_id=fc.id,
            )
            result = await self.tool_adapter.execute_tool(fc.name, fc.args or {})
            responses.append(
                {
                    "name": fc.name,
                    "response": result,
                    "id": fc.id,
                }
            )
            tool_names.append(fc.name)

            # Log tool call in conversation
            session_id = self.ensure_conversation_session()
            if self.conv_manager is not None and session_id is not None:
                self.conv_manager.add_turn(
                    session_id,
                    "system",
                    f"Tool call: {fc.name}",
                    metadata={
                        "tool_call": fc.name,
                        "args": fc.args,
                        "result": result,
                    },
                )

        # Send all responses back to the realtime provider.
        if responses and self.provider and self._current_session:
            await self.provider.send_tool_response(self._current_session, responses)

        # Notify client that tools were called (UX signal)
        await self.ws.send_json(
            {
                "type": "tool_calls",
                "tools": tool_names,
            }
        )

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
        if self._replay:
            return
        while not self._client_disconnected.is_set():
            try:
                item = await asyncio.wait_for(self._client_to_backend.get(), timeout=1.0)
            except TimeoutError:
                continue
            if item[0] in ("sync_instruction", "wake"):
                # No session is open, so the next one already uses the current
                # instruction; opening a paid session just to apply it is waste.
                continue
            if item[0] == "prompt":
                # Open the session with the prompt's instruction rather than opening
                # one with the old instruction only to replace it.
                self._adopt_prompt_instruction(item[1])
            self._replay.append(item)
            return

    def _adopt_prompt_instruction(self, payload: tuple) -> None:
        """Make a prompt's system instruction (if any) current and record its owner."""
        _text, _callback, exp, voice_instruction, metadata = payload
        if voice_instruction and time.time() <= exp:
            self._current_voice_instruction = voice_instruction
            self._voice_instruction_owner = voice_owner_for(metadata)

    def _turn_in_progress(self) -> bool:
        """An orchestrator prompt awaits its reply, or the model is mid-turn."""
        return self._is_orchestrator_turn or self._model_turn_active

    def _release_held_prompts(self) -> None:
        """Put held prompts first in line, in their original order."""
        self._replay.extendleft(reversed(self._held_prompts))
        self._held_prompts.clear()

    def _reset_turn_state(self) -> None:
        """A session ended: no turn survives it, and held prompts go to the next one."""
        self._model_turn_active = False
        self._sync_after_turn = False
        self._is_orchestrator_turn = False
        self._release_held_prompts()

    async def _next_backend_item(self) -> tuple[str, Any]:
        """Return a held item first, then the next one from the client/prompt queue."""
        if self._replay:
            return self._replay.popleft()
        return await self._client_to_backend.get()

    @property
    def conversation_session_id(self) -> int | None:
        """The ``conversation_sessions`` row this socket's turns are written to, or
        None while the socket has had no activity."""
        return self._session_id

    def ensure_conversation_session(self) -> int | None:
        """The socket's conversation row, created on first need.

        First need is the first turn written, or a guided routine beginning on this
        screen (it is about to speak, and its transcript must be this conversation).
        On creation, live guided sessions with no conversation yet are linked to it,
        fire-and-forget, as on connect before. None without a conversation manager.
        """
        if self.conv_manager is None:
            return None
        if self._session_id is None:
            self._session_id = self.conv_manager.create_session()
            guided_task_service = getattr(self.ws.app.state, "guided_task_service", None)
            if guided_task_service is not None:
                asyncio.create_task(  # noqa: RUF006
                    guided_task_service.on_conversation_started(self._session_id),
                    name="guided-on-conversation-started",
                )
        return self._session_id

    def enqueue_prompt(self, item: PromptItem) -> None:
        """Take a prompt routed to this session's surface (see ``send_backend_task``)."""
        self._client_to_backend.put_nowait(("prompt", item))

    async def release_voice_instruction(self, owner: str) -> bool:
        """Restore the base persona if ``owner`` set the active system instruction.

        Returns whether this handler held ``owner``'s instruction. An open realtime
        session is ended between turns (never mid-sentence) so the next one opens with
        the base persona; an idle handler is not woken.
        """
        if owner is None or owner != self._voice_instruction_owner:
            return False
        self._current_voice_instruction = None
        self._voice_instruction_owner = None
        if self._backend_active:
            if self._model_turn_active:
                self._sync_after_turn = True
            else:
                await self._client_to_backend.put(("sync_instruction", None))
        logger.info("ws_voice_instruction_release_requested")
        return True

    async def _no_backend_fallback(self) -> None:
        """Keep the WebSocket alive for push notifications when no AI backend."""
        await self.ws.send_json({"type": "error", "message": "Backend AI not configured."})
        await self._client_disconnected.wait()

    async def _handle_interactive_response(self, data: dict) -> None:
        """Handle interactive_response WebSocket message.

        Validates the payload, records the response via InteractiveResponseService,
        and sends acknowledgment back to the client.

        Args:
            data: Raw message data from WebSocket
        """

        try:
            # Validate payload using Pydantic schema
            message = InteractiveResponseMessage(**data)

            # Validate action field
            if message.action not in ("escalate", "dismiss"):
                raise ValueError(f"Invalid action: {message.action}")

            # Get InteractiveResponseService from app state
            interactive_service: InteractiveResponseService | None = (
                self.ws.app.state.interactive_response_service
            )

            if interactive_service is None:
                logger.error("interactive_response_service_not_configured")
                await self.ws.send_json(
                    {
                        "type": "error",
                        "message": "Interactive response service not configured",
                    }
                )
                return

            # Record the response
            response = await interactive_service.record_response(
                execution_id=message.execution_id,
                step_id=message.step_id,
                channel="pwa_popup_text",
                action=message.action,
                timestamp=message.timestamp,
                raw_response={"button_id": message.action},
            )

            # Send acknowledgment to client
            if response is not None:
                await self.ws.send_json(
                    {
                        "type": "interactive_response_ack",
                        "execution_id": message.execution_id,
                        "step_id": message.step_id,
                        "status": "success",
                    }
                )
                logger.info(
                    "interactive_response_handled",
                    execution_id=message.execution_id,
                    step_id=message.step_id,
                    action=message.action,
                )
            else:
                # Duplicate response - still send success ack (idempotent)
                await self.ws.send_json(
                    {
                        "type": "interactive_response_ack",
                        "execution_id": message.execution_id,
                        "step_id": message.step_id,
                        "status": "duplicate",
                    }
                )
                logger.info(
                    "interactive_response_duplicate_ack",
                    execution_id=message.execution_id,
                    step_id=message.step_id,
                )

        except ValidationError as e:
            # Validation error - log and send error response
            logger.error(
                "interactive_response_validation_error",
                error=str(e),
                data=data,
            )
            await self.ws.send_json(
                {
                    "type": "error",
                    "message": f"Invalid interactive_response payload: {e}",
                }
            )

        except ValueError as e:
            # Invalid action or other value error
            logger.error(
                "interactive_response_value_error",
                error=str(e),
                data=data,
            )
            await self.ws.send_json(
                {
                    "type": "error",
                    "message": str(e),
                }
            )

        except Exception as e:
            # Unexpected error - log and send error response
            logger.error(
                "interactive_response_handler_error",
                error=str(e),
                data=data,
            )
            await self.ws.send_json(
                {
                    "type": "error",
                    "message": "Failed to process interactive response",
                }
            )

    async def _handle_quiz_answer(self, data: dict) -> None:
        """Handle quiz_answer WebSocket message from the PWA."""
        session_id = data.get("session_id")
        question_ord = data.get("question_ord")
        choice_id = data.get("choice_id")
        open_ended_text = data.get("open_ended_text")
        latency_ms = data.get("latency_ms")

        if session_id is None or question_ord is None:
            logger.error("quiz_answer_missing_fields", data=data)
            return

        delivery: KnowledgeDeliveryService | None = self.ws.app.state.knowledge_delivery
        if delivery is None:
            logger.error("quiz_answer_no_delivery_service")
            return

        try:
            await delivery.submit_quiz_answer(
                session_id=session_id,
                question_ord=question_ord,
                choice_id=choice_id,
                open_ended_text=open_ended_text,
                channel="pwa",
                latency_ms=latency_ms,
            )
        except Exception:
            logger.exception("quiz_answer_handler_error", session_id=session_id)

    async def _handle_info_card_event(self, data: dict) -> None:
        """Handle info_card_dismiss WebSocket message from the PWA."""
        delivery_id = data.get("delivery_id")
        action = data.get("action", "dismissed")

        if delivery_id is None:
            logger.error("info_card_event_missing_delivery_id", data=data)
            return

        delivery: KnowledgeDeliveryService | None = self.ws.app.state.knowledge_delivery
        if delivery is None:
            logger.error("info_card_event_no_delivery_service")
            return

        try:
            await delivery.handle_info_card_event(delivery_id, action)
        except Exception:
            logger.exception("info_card_event_handler_error", delivery_id=delivery_id)

    def _handle_surface_attention(self, data: dict) -> None:
        """Record whether someone is facing this surface (no image, no identity).

        Readings from a socket with no surface are ignored: attention only means
        something for a registered surface in a known room.
        """
        if self.surface_id is None:
            logger.warning("surface_attention_without_surface")
            return
        try:
            reading = SurfaceAttentionStateIn.model_validate(data)
        except ValidationError:
            logger.warning("surface_attention_invalid", surface_id=self.surface_id)
            return
        self.manager.record_attention(self.surface_id, reading)

    async def _handle_guided_step_action(self, data: dict) -> None:
        """A tap on the resident's guided-task widget (I'm Done, Repeat, I Need Help).

        The service decides everything, including speaking the next step through
        the normal voice path, so the agent hears it with its ``[step_ord]``
        marker. Only the tapping tablet is answered, so its buttons never stay
        busy when the tap changed nothing (a stale screen, a held gate).
        """
        try:
            action = GuidedStepActionIn.model_validate(data)
        except ValidationError:
            logger.warning("guided_step_action_invalid", data=data)
            return

        accepted, reason = False, "unavailable"
        guided = getattr(self.ws.app.state, "guided_task_service", None)
        if guided is None:
            logger.error("guided_step_action_no_service")
        else:
            try:
                result = await guided.handle_surface_action(
                    action.session_id, action.action, step_ord=action.step_ord
                )
                accepted, reason = bool(result.get("accepted")), result.get("reason")
            except NotFoundError:
                reason = "session_not_found"
            except Exception:
                logger.exception(
                    "guided_step_action_failed",
                    session_id=action.session_id,
                    action=action.action,
                )
                reason = "failed"
        ack = GuidedStepActionResultEvent(
            session_id=action.session_id, action=action.action, accepted=accepted, reason=reason
        )
        try:
            await self.ws.send_json(ack.model_dump(mode="json"))
        except Exception:
            logger.warning("guided_step_action_ack_failed", session_id=action.session_id)
