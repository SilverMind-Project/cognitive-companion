"""The audio session's side of surface routing: its prompt inbox and attention intake."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.websocket.audio_handler import AudioSessionHandler
from backend.websocket.connection_manager import ConnectionManager


def _handler(surface_id: str | None) -> tuple[AudioSessionHandler, ConnectionManager]:
    ws = AsyncMock()
    ws.app = MagicMock()
    manager = ConnectionManager()
    handler = AudioSessionHandler(
        websocket=ws, manager=manager, realtime_provider=None, surface_id=surface_id
    )
    return handler, manager


@pytest.mark.asyncio
async def test_a_prompt_routed_to_this_surface_wakes_its_session() -> None:
    handler, manager = _handler("kitchen-tablet")
    manager.register_audio_handler(handler, surface_id="kitchen-tablet")

    await manager.send_backend_task("Fill the kettle.", surface_id="kitchen-tablet")

    kind, item = await handler._next_backend_item()
    assert kind == "prompt"
    assert item[0] == "Fill the kettle."
    assert manager.prompt_queue.empty()


def test_attention_reading_is_recorded_for_the_authenticated_surface() -> None:
    handler, manager = _handler("kitchen-tablet")

    handler._handle_surface_attention(
        {
            "type": "surface_attention_state",
            "face_present": True,
            "head_yaw_deg": -4.2,
            "head_pitch_deg": 1.5,
        }
    )

    reading = manager.latest_attention("kitchen-tablet")
    assert reading is not None
    assert (reading.face_present, reading.head_yaw_deg) == (True, -4.2)


@pytest.mark.parametrize(
    ("surface_id", "message"),
    [
        # A socket with no surface has no room for the reading to describe.
        (None, {"type": "surface_attention_state", "face_present": True}),
        # An image never leaves the tablet.
        (
            "kitchen-tablet",
            {"type": "surface_attention_state", "face_present": True, "snapshot_base64": "AA"},
        ),
        # A client cannot report on another surface's behalf.
        (
            "kitchen-tablet",
            {"type": "surface_attention_state", "face_present": True, "surface_id": "bedroom"},
        ),
    ],
)
def test_attention_readings_that_are_dropped(surface_id: str | None, message: dict) -> None:
    handler, manager = _handler(surface_id)

    handler._handle_surface_attention(message)

    assert manager.latest_attention("kitchen-tablet") is None
    assert manager.latest_attention("bedroom") is None
