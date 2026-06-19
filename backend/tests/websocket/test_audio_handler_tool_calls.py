"""Tests for realtime audio handler tool-call plumbing."""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_handle_tool_calls_sends_provider_neutral_responses() -> None:
    ws = AsyncMock()
    ws.app = MagicMock()
    ws.app.state = MagicMock()
    manager = MagicMock()
    provider = AsyncMock()
    tool_adapter = AsyncMock()
    tool_adapter.execute_tool = AsyncMock(return_value={"ok": True})
    session = RealtimeSession(session_object=object())
    handler = AudioSessionHandler(
        websocket=ws,
        manager=manager,
        realtime_provider=provider,
        tool_adapter=tool_adapter,
    )
    handler._current_session = session

    await handler._handle_tool_calls(
        [_FunctionCall(name="get_active_guided_step", args={}, id="c1")]
    )

    provider.send_tool_response.assert_awaited_once_with(
        session,
        [{"name": "get_active_guided_step", "response": {"ok": True}, "id": "c1"}],
    )
    ws.send_json.assert_awaited_once_with(
        {"type": "tool_calls", "tools": ["get_active_guided_step"]}
    )
