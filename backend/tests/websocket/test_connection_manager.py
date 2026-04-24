"""Tests for ConnectionManager binary broadcast."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.websocket.connection_manager import ConnectionManager


def _make_ws(healthy: bool = True) -> AsyncMock:
    ws = AsyncMock()
    if not healthy:
        ws.send_bytes = AsyncMock(side_effect=Exception("stale"))
        ws.send_json = AsyncMock(side_effect=Exception("stale"))
    return ws


class TestBroadcastBytes:
    @pytest.mark.asyncio
    async def test_sends_to_all_clients(self):
        mgr = ConnectionManager()
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.active_connections = [ws1, ws2]

        await mgr.broadcast_bytes(b"\x00\x01\x02")

        ws1.send_bytes.assert_called_once_with(b"\x00\x01\x02")
        ws2.send_bytes.assert_called_once_with(b"\x00\x01\x02")

    @pytest.mark.asyncio
    async def test_removes_stale_connections(self):
        mgr = ConnectionManager()
        healthy_ws = _make_ws()
        stale_ws = _make_ws(healthy=False)
        mgr.active_connections = [healthy_ws, stale_ws]

        await mgr.broadcast_bytes(b"\x00")

        healthy_ws.send_bytes.assert_called_once()
        # Stale connection should be removed
        assert stale_ws not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_empty_connections_is_noop(self):
        mgr = ConnectionManager()
        mgr.active_connections = []
        await mgr.broadcast_bytes(b"\x00")  # should not raise


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_sends_json_to_all(self):
        mgr = ConnectionManager()
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.active_connections = [ws1, ws2]

        await mgr.broadcast({"type": "test", "message": "hello"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_removes_stale_on_json_broadcast(self):
        mgr = ConnectionManager()
        healthy_ws = _make_ws()
        stale_ws = _make_ws(healthy=False)
        mgr.active_connections = [healthy_ws, stale_ws]

        await mgr.broadcast({"type": "test"})
        assert stale_ws not in mgr.active_connections

    @pytest.mark.asyncio
    async def test_broadcasts_interactive_prompt_with_all_fields(self):
        """Test that interactive_prompt messages are broadcast with all required fields."""
        mgr = ConnectionManager()
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.active_connections = [ws1, ws2]

        # Simulate the interactive_prompt message sent by InteractivePromptHandler
        interactive_prompt_payload = {
            "type": "interactive_prompt",
            "execution_id": 123,
            "step_id": 456,
            "message": "Are you okay? Do you need help?",
            "escalate_button_text": "I need help",
            "dismiss_button_text": "I'm okay",
            "countdown_seconds": 30,
            "server_timestamp": "2024-01-15T10:30:00Z",
        }

        await mgr.broadcast(interactive_prompt_payload)

        # Verify both clients received the message
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

        # Verify the message structure
        sent_message = ws1.send_json.call_args[0][0]
        assert sent_message["type"] == "interactive_prompt"
        assert sent_message["execution_id"] == 123
        assert sent_message["step_id"] == 456
        assert sent_message["message"] == "Are you okay? Do you need help?"
        assert sent_message["escalate_button_text"] == "I need help"
        assert sent_message["dismiss_button_text"] == "I'm okay"
        assert sent_message["countdown_seconds"] == 30
        assert sent_message["server_timestamp"] == "2024-01-15T10:30:00Z"
