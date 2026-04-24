"""Tests for interactive_response WebSocket message handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.websocket.audio_handler import AudioSessionHandler


def _make_ws() -> AsyncMock:
    """Create a mock WebSocket with app.state."""
    ws = AsyncMock()
    ws.app = MagicMock()
    ws.app.state = MagicMock()
    return ws


def _make_interactive_service(response_result=MagicMock()) -> AsyncMock:
    """Create a mock InteractiveResponseService."""
    service = AsyncMock()
    service.record_response = AsyncMock(return_value=response_result)
    return service


class TestInteractiveResponseHandler:
    """Tests for _handle_interactive_response method."""

    @pytest.mark.asyncio
    async def test_valid_response_recorded_and_ack_sent(self):
        """Test that a valid response is recorded and acknowledgment is sent."""
        ws = _make_ws()
        manager = MagicMock()

        # Create mock response object
        mock_response = MagicMock()
        mock_response.id = 1

        interactive_service = _make_interactive_service(response_result=mock_response)
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        # Valid interactive_response message
        message_data = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "escalate",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(message_data)

        # Verify service was called with correct parameters
        interactive_service.record_response.assert_called_once()
        call_args = interactive_service.record_response.call_args
        assert call_args.kwargs["execution_id"] == 123
        assert call_args.kwargs["step_id"] == 456
        assert call_args.kwargs["channel"] == "pwa_popup_text"
        assert call_args.kwargs["action"] == "escalate"
        assert call_args.kwargs["raw_response"] == {"button_id": "escalate"}

        # Verify acknowledgment was sent
        ws.send_json.assert_called_once()
        ack_message = ws.send_json.call_args[0][0]
        assert ack_message["type"] == "interactive_response_ack"
        assert ack_message["execution_id"] == 123
        assert ack_message["step_id"] == 456
        assert ack_message["status"] == "success"

    @pytest.mark.asyncio
    async def test_duplicate_response_sends_duplicate_ack(self):
        """Test that duplicate responses are handled gracefully."""
        ws = _make_ws()
        manager = MagicMock()

        # Service returns None for duplicate
        interactive_service = _make_interactive_service(response_result=None)
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        message_data = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "dismiss",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(message_data)

        # Verify acknowledgment was sent with duplicate status
        ws.send_json.assert_called_once()
        ack_message = ws.send_json.call_args[0][0]
        assert ack_message["type"] == "interactive_response_ack"
        assert ack_message["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_invalid_payload_sends_error(self):
        """Test that invalid payloads are rejected with error message."""
        ws = _make_ws()
        manager = MagicMock()
        interactive_service = _make_interactive_service()
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        # Missing required field (step_id)
        invalid_message = {
            "type": "interactive_response",
            "execution_id": 123,
            "action": "escalate",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(invalid_message)

        # Verify error was sent
        ws.send_json.assert_called_once()
        error_message = ws.send_json.call_args[0][0]
        assert error_message["type"] == "error"
        assert "Invalid interactive_response payload" in error_message["message"]

        # Verify service was NOT called
        interactive_service.record_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_action_sends_error(self):
        """Test that invalid action values are rejected."""
        ws = _make_ws()
        manager = MagicMock()
        interactive_service = _make_interactive_service()
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        # Invalid action value
        invalid_message = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "invalid_action",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(invalid_message)

        # Verify error was sent
        ws.send_json.assert_called_once()
        error_message = ws.send_json.call_args[0][0]
        assert error_message["type"] == "error"
        assert "Invalid action" in error_message["message"]

        # Verify service was NOT called
        interactive_service.record_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_service_not_configured_sends_error(self):
        """Test that missing service configuration is handled."""
        ws = _make_ws()
        manager = MagicMock()
        ws.app.state.interactive_response_service = None  # Service not configured

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        message_data = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "escalate",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(message_data)

        # Verify error was sent
        ws.send_json.assert_called_once()
        error_message = ws.send_json.call_args[0][0]
        assert error_message["type"] == "error"
        assert "not configured" in error_message["message"]

    @pytest.mark.asyncio
    async def test_service_exception_sends_error(self):
        """Test that service exceptions are caught and error is sent."""
        ws = _make_ws()
        manager = MagicMock()

        # Service raises exception
        interactive_service = AsyncMock()
        interactive_service.record_response = AsyncMock(
            side_effect=Exception("Database error")
        )
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        message_data = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "escalate",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(message_data)

        # Verify error was sent
        ws.send_json.assert_called_once()
        error_message = ws.send_json.call_args[0][0]
        assert error_message["type"] == "error"
        assert "Failed to process" in error_message["message"]

    @pytest.mark.asyncio
    async def test_dismiss_action_is_valid(self):
        """Test that 'dismiss' action is accepted."""
        ws = _make_ws()
        manager = MagicMock()

        mock_response = MagicMock()
        interactive_service = _make_interactive_service(response_result=mock_response)
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        message_data = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "dismiss",
            "timestamp": "2024-01-15T10:30:15Z",
        }

        await handler._handle_interactive_response(message_data)

        # Verify service was called with dismiss action
        interactive_service.record_response.assert_called_once()
        call_args = interactive_service.record_response.call_args
        assert call_args.kwargs["action"] == "dismiss"

        # Verify success ack was sent
        ws.send_json.assert_called_once()
        ack_message = ws.send_json.call_args[0][0]
        assert ack_message["status"] == "success"

    @pytest.mark.asyncio
    async def test_late_response_after_timeout_ignored(self):
        """Test that late responses after timeout are handled as duplicates.

        Scenario: A timeout has already occurred and created a synthetic response.
        The user then sends a response after the timeout. The system should
        ignore the late response (service returns None for duplicate).
        """
        ws = _make_ws()
        manager = MagicMock()

        # Service returns None indicating a response already exists (from timeout)
        interactive_service = _make_interactive_service(response_result=None)
        ws.app.state.interactive_response_service = interactive_service

        handler = AudioSessionHandler(
            websocket=ws,
            manager=manager,
            realtime_provider=None,
        )

        # User sends response after timeout has already fired
        message_data = {
            "type": "interactive_response",
            "execution_id": 123,
            "step_id": 456,
            "action": "escalate",
            "timestamp": "2024-01-15T10:30:45Z",  # Late timestamp
        }

        await handler._handle_interactive_response(message_data)

        # Verify service was called (attempt to record)
        interactive_service.record_response.assert_called_once()

        # Verify duplicate acknowledgment was sent (idempotent behavior)
        ws.send_json.assert_called_once()
        ack_message = ws.send_json.call_args[0][0]
        assert ack_message["type"] == "interactive_response_ack"
        assert ack_message["execution_id"] == 123
        assert ack_message["step_id"] == 456
        assert ack_message["status"] == "duplicate"
