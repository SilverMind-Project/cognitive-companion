"""Voice-instruction lifecycle of the realtime audio handler.

A fake realtime provider records which session each prompt is sent to and which
session is being read, so a reconnect that strands the prompt on an unread session
shows up as a failed assertion rather than as silence on the tablet.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations.llm.base import RealtimeSession
from backend.websocket.audio_handler import AudioSessionHandler
from backend.websocket.connection_manager import ConnectionManager

BASE = "BASE PERSONA"


@dataclass
class _FakeSessionState:
    index: int
    instruction: str
    responses: asyncio.Queue = field(default_factory=asyncio.Queue)
    sent: list[str] = field(default_factory=list)
    closed: bool = False
    read: bool = False


class _FakeProvider:
    configured = True

    def __init__(self) -> None:
        self.sessions: list[_FakeSessionState] = []
        self.prompt_delivered = asyncio.Event()
        self.session_closed = asyncio.Event()

    def build_config(self, system_instruction: str = "", **_: Any) -> dict[str, Any]:
        return {"instruction": system_instruction or BASE}

    async def connect(self, config: dict[str, Any]) -> RealtimeSession:
        state = _FakeSessionState(index=len(self.sessions), instruction=config["instruction"])
        self.sessions.append(state)
        return RealtimeSession(session_object=state)

    async def disconnect(self, session: RealtimeSession) -> None:
        state: _FakeSessionState = session.session_object
        state.closed = True
        self.session_closed.set()
        await state.responses.put(None)

    async def send_text(self, session: RealtimeSession, text: str) -> None:
        state: _FakeSessionState = session.session_object
        state.sent.append(text)
        turn = SimpleNamespace(
            tool_call=None,
            tool_call_cancellation=None,
            server_content=SimpleNamespace(
                model_turn=None,
                output_transcription=SimpleNamespace(text="spoken"),
                input_transcription=None,
                turn_complete=True,
            ),
        )
        # A real model answers after a delay; an instant reply hides races with
        # whatever the handler does next.
        asyncio.get_running_loop().call_later(0.05, state.responses.put_nowait, turn)

    async def send_audio(self, session: RealtimeSession, data: bytes) -> None:
        return None

    async def receive(self, session: RealtimeSession):
        state: _FakeSessionState = session.session_object
        state.read = True
        while True:
            item = await state.responses.get()
            if item is None:
                raise ConnectionError("session closed")
            yield item
            if state.sent and not state.closed:
                self.prompt_delivered.set()


class _BlockingWebSocket:
    def __init__(self) -> None:
        self.app = MagicMock()
        self.app.state = SimpleNamespace(guided_task_service=None)
        self.send_json = AsyncMock()
        self.send_bytes = AsyncMock()
        self._gone = asyncio.Event()

    async def receive(self) -> dict[str, Any]:
        await self._gone.wait()
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect()

    def leave(self) -> None:
        self._gone.set()


async def _run_until(handler_task: asyncio.Task, event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=5)


@pytest.mark.asyncio
async def test_prompt_with_new_voice_instruction_reaches_a_session_that_is_read() -> None:
    provider = _FakeProvider()
    manager = ConnectionManager()
    ws = _BlockingWebSocket()
    handler = AudioSessionHandler(websocket=ws, manager=manager, realtime_provider=provider)
    task = asyncio.create_task(handler.run())
    try:
        await manager.send_backend_task(
            prompt="First question",
            voice_instruction=f"{BASE}\n\nQUIZ",
            metadata={"delivery_type": "quiz_start", "session_id": 7},
        )
        await _run_until(task, provider.prompt_delivered)
    finally:
        ws.leave()
        await asyncio.wait_for(task, timeout=5)

    delivered = [s for s in provider.sessions if any("First question" in t for t in s.sent)]
    assert len(delivered) == 1
    session = delivered[0]
    assert session.read, "the prompt went to a session nobody reads"
    assert session.instruction == f"{BASE}\n\nQUIZ"
    assert all(s.closed for s in provider.sessions), "a realtime session leaked"


class _Harness:
    """Runs one handler against the fake provider for the duration of a test."""

    def __init__(self, manager: ConnectionManager | None = None) -> None:
        self.provider = _FakeProvider()
        self.manager = manager or ConnectionManager()
        self.ws = _BlockingWebSocket()
        self.handler = AudioSessionHandler(
            websocket=self.ws, manager=self.manager, realtime_provider=self.provider
        )
        self.task: asyncio.Task | None = None

    async def __aenter__(self) -> _Harness:
        self.task = asyncio.create_task(self.handler.run())
        # One loop turn lets run() register the handler with the manager.
        await asyncio.sleep(0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.ws.leave()
        assert self.task is not None
        await asyncio.wait_for(self.task, timeout=5)

    async def prompt(self, text: str, instruction: str | None, owner_session: int) -> None:
        self.provider.prompt_delivered.clear()
        await self.manager.send_backend_task(
            prompt=text,
            voice_instruction=instruction,
            metadata={"delivery_type": "quiz_start", "session_id": owner_session},
        )
        await asyncio.wait_for(self.provider.prompt_delivered.wait(), timeout=5)

    async def session_closed(self) -> None:
        await asyncio.wait_for(self.provider.session_closed.wait(), timeout=5)


QUIZ = f"{BASE}\n\nQUIZ"


@pytest.mark.asyncio
async def test_new_instruction_opens_one_session_not_a_throwaway_base_session() -> None:
    async with _Harness() as h:
        await h.prompt("First question", QUIZ, owner_session=7)

    assert [s.instruction for s in h.provider.sessions] == [QUIZ]


@pytest.mark.asyncio
async def test_owner_release_ends_session_and_next_session_uses_base_persona() -> None:
    async with _Harness() as h:
        await h.prompt("First question", QUIZ, owner_session=7)

        released = await h.manager.release_voice_instruction("quiz_start:7")
        await h.session_closed()
        assert len(h.provider.sessions) == 1, "release must not open a new session"

        await h.prompt("How are you?", None, owner_session=8)

    assert released is True
    assert [s.instruction for s in h.provider.sessions] == [QUIZ, BASE]


@pytest.mark.asyncio
async def test_release_by_another_delivery_keeps_the_running_instruction() -> None:
    async with _Harness() as h:
        await h.prompt("First question", QUIZ, owner_session=7)

        released = await h.manager.release_voice_instruction("info_card:7")
        await h.prompt("Second question", None, owner_session=7)

    assert released is False
    assert len(h.provider.sessions) == 1
    assert h.provider.sessions[0].sent[-1].endswith("Second question")
    assert h.provider.sessions[0].closed  # only by the harness teardown


@pytest.mark.asyncio
async def test_release_while_idle_does_not_open_a_session() -> None:
    async with _Harness() as h:
        h.handler._current_voice_instruction = QUIZ
        h.handler._voice_instruction_owner = "quiz_start:7"

        released = await h.manager.release_voice_instruction("quiz_start:7")
        await h.prompt("Hello", None, owner_session=9)

    assert released is True
    assert [s.instruction for s in h.provider.sessions] == [BASE]


@pytest.mark.asyncio
async def test_release_mid_turn_waits_for_turn_complete() -> None:
    async with _Harness() as h:
        await h.prompt("First question", QUIZ, owner_session=7)
        h.handler._model_turn_active = True

        await h.manager.release_voice_instruction("quiz_start:7")
        assert h.handler._sync_after_turn is True
        assert not h.provider.sessions[0].closed

        await h.prompt("Closing words", None, owner_session=7)
        await h.session_closed()


@pytest.mark.asyncio
async def test_handler_unregisters_from_manager_on_disconnect() -> None:
    manager = ConnectionManager()
    async with _Harness(manager) as h:
        assert h.handler in manager._audio_handlers

    assert h.handler not in manager._audio_handlers


@pytest.mark.asyncio
async def test_new_instruction_waits_for_the_turn_being_spoken() -> None:
    """A card and a quiz delivered back to back: the card must be spoken in full before
    the quiz's instruction reopens the session (live, the card was cut off unheard)."""
    async with _Harness() as h:
        await h.manager.send_backend_task(
            prompt="Here is some information for you.",
            voice_instruction=f"{BASE}\n\nCARD",
            metadata={"delivery_type": "info_card", "delivery_id": 3},
        )
        await h.manager.send_backend_task(
            prompt="First question",
            voice_instruction=QUIZ,
            metadata={"delivery_type": "quiz_start", "session_id": 7},
        )
        await h.session_closed()  # the card session ends only after its turn
        h.provider.prompt_delivered.clear()
        await asyncio.wait_for(h.provider.prompt_delivered.wait(), timeout=5)

    card_session, quiz_session = h.provider.sessions
    assert card_session.instruction == f"{BASE}\n\nCARD"
    assert card_session.sent == ["Here is some information for you."]
    assert quiz_session.instruction == QUIZ
    assert quiz_session.sent[-1].endswith("First question")
    spoken = [
        call.args[0]
        for call in h.ws.send_json.await_args_list
        if call.args[0].get("type") == "transcript" and call.args[0].get("source") == "assistant"
    ]
    assert len(spoken) == 2, "the card's turn must complete before the session is replaced"


@pytest.mark.asyncio
async def test_release_after_turn_releases_persona_automatically() -> None:
    """A voice-only info card sets release_after_turn so persona reverts after its turn."""
    async with _Harness() as h:
        await h.manager.send_backend_task(
            prompt="Remember to drink some water.",
            voice_instruction=f"{BASE}\n\nCARD",
            metadata={
                "delivery_type": "info_card",
                "delivery_id": 11,
                "release_after_turn": True,
            },
        )
        await h.session_closed()

        await h.prompt("How are you today?", None, owner_session=12)

    assert [s.instruction for s in h.provider.sessions] == [f"{BASE}\n\nCARD", BASE]
