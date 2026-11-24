"""The ``guided_step_action`` message from the resident's guided-task widget."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.exceptions import NotFoundError
from backend.websocket.audio_handler import AudioSessionHandler


def _handler(guided_service) -> tuple[AudioSessionHandler, AsyncMock]:
    ws = AsyncMock()
    ws.app = MagicMock()
    ws.app.state = MagicMock()
    ws.app.state.guided_task_service = guided_service
    return AudioSessionHandler(websocket=ws, manager=MagicMock(), realtime_provider=None), ws


@pytest.mark.asyncio
async def test_done_tap_goes_to_the_service_and_only_the_tapper_is_answered() -> None:
    service = MagicMock()
    service.handle_surface_action = AsyncMock(
        return_value={"accepted": True, "reason": None, "advanced": True}
    )
    handler, ws = _handler(service)

    await handler._handle_guided_step_action(
        {"type": "guided_step_action", "session_id": 7, "action": "done", "step_ord": 1}
    )

    service.handle_surface_action.assert_awaited_once_with(7, "done", step_ord=1)
    ws.send_json.assert_awaited_once_with(
        {
            "type": "guided_step_action_result",
            "session_id": 7,
            "action": "done",
            "accepted": True,
            "reason": None,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["repeat", "help"])
async def test_repeat_and_help_need_no_step_ord(action: str) -> None:
    service = MagicMock()
    service.handle_surface_action = AsyncMock(return_value={"accepted": True, "reason": None})
    handler, _ws = _handler(service)

    await handler._handle_guided_step_action(
        {"type": "guided_step_action", "session_id": 7, "action": action}
    )

    service.handle_surface_action.assert_awaited_once_with(7, action, step_ord=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        {"type": "guided_step_action", "session_id": "7", "action": "done", "step_ord": 0},
        {"type": "guided_step_action", "session_id": 7, "action": "skip"},
        {"type": "guided_step_action", "action": "help"},
    ],
)
async def test_malformed_taps_are_dropped(message: dict) -> None:
    service = MagicMock()
    service.handle_surface_action = AsyncMock()
    handler, ws = _handler(service)

    await handler._handle_guided_step_action(message)

    service.handle_surface_action.assert_not_awaited()
    ws.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_session_and_failures_still_release_the_buttons() -> None:
    service = MagicMock()
    service.handle_surface_action = AsyncMock(side_effect=NotFoundError("Guided session", 9))
    handler, ws = _handler(service)

    await handler._handle_guided_step_action(
        {"type": "guided_step_action", "session_id": 9, "action": "help"}
    )
    service.handle_surface_action.side_effect = RuntimeError("boom")
    await handler._handle_guided_step_action(
        {"type": "guided_step_action", "session_id": 9, "action": "help"}
    )

    reasons = [call.args[0]["reason"] for call in ws.send_json.await_args_list]
    accepted = [call.args[0]["accepted"] for call in ws.send_json.await_args_list]
    assert reasons == ["session_not_found", "failed"]
    assert accepted == [False, False]


@pytest.mark.asyncio
async def test_receive_loop_dispatches_guided_step_action() -> None:
    handler, ws = _handler(MagicMock())
    handler._handle_guided_step_action = AsyncMock()
    from fastapi import WebSocketDisconnect

    ws.receive = AsyncMock(
        side_effect=[
            {"text": '{"type": "guided_step_action", "session_id": 1, "action": "help"}'},
            WebSocketDisconnect(),
        ]
    )

    await handler._receive_from_client()

    handler._handle_guided_step_action.assert_awaited_once()
