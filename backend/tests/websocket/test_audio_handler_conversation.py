"""A companion socket creates its conversation row on first activity, never on connect.

Every idle screen reconnect used to leave an empty ``conversation_sessions`` row
behind. The row now appears with the first turn written (or when a routine begins on
that screen), and live guided sessions are linked to it then.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations.llm.base import RealtimeSession
from backend.websocket.audio_handler import AudioSessionHandler


@dataclass(frozen=True)
class _FunctionCall:
    name: str
    args: dict
    id: str


def _handler(*, provider=None, tool_adapter=None):
    ws = AsyncMock()
    ws.app = MagicMock()
    guided = MagicMock()
    guided.on_session_opened = AsyncMock()
    guided.on_conversation_started = AsyncMock()
    ws.app.state = MagicMock(guided_task_service=guided)
    conversations = MagicMock()
    conversations.create_session = MagicMock(side_effect=[41, 42])
    handler = AudioSessionHandler(
        websocket=ws,
        manager=MagicMock(),
        realtime_provider=provider,
        conversation_manager=conversations,
        tool_adapter=tool_adapter,
    )
    return handler, conversations, guided


@pytest.mark.asyncio
async def test_a_connection_with_no_activity_leaves_no_conversation_behind() -> None:
    handler, conversations, guided = _handler()
    handler.ws.receive = AsyncMock(return_value={"type": "websocket.disconnect", "code": 1000})

    await asyncio.wait_for(handler.run(), timeout=5)
    await asyncio.sleep(0)

    conversations.create_session.assert_not_called()
    conversations.end_session.assert_not_called()
    assert handler.conversation_session_id is None
    # The summoning re-check still runs on connect.
    guided.on_session_opened.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_the_conversation_is_created_once_and_linked_when_first_needed() -> None:
    handler, conversations, guided = _handler()

    first = handler.ensure_conversation_session()
    again = handler.ensure_conversation_session()
    await asyncio.sleep(0)

    assert first == again == 41
    conversations.create_session.assert_called_once_with()
    guided.on_conversation_started.assert_awaited_once_with(41, surface_id=None)


@pytest.mark.asyncio
async def test_the_first_tool_call_writes_to_a_newly_created_conversation() -> None:
    tool_adapter = AsyncMock()
    tool_adapter.execute_tool = AsyncMock(return_value={"ok": True})
    handler, conversations, _guided = _handler(provider=AsyncMock(), tool_adapter=tool_adapter)
    handler._current_session = RealtimeSession(session_object=object())

    await handler._handle_tool_calls([_FunctionCall(name="get_rooms", args={}, id="c1")])

    conversations.create_session.assert_called_once_with()
    session_id, role, text = conversations.add_turn.call_args.args
    assert (session_id, role, text) == (41, "system", "Tool call: get_rooms")
