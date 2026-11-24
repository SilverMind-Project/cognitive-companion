"""Room-targeted delivery on the companion socket (``ConnectionManager``).

A delivery for the resident goes to the companion surface in her room. Content falls
back to every companion screen when that surface is offline; a wake or capture
command never does, because opening a microphone in an empty room is a privacy
failure, not a degraded delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from backend.schemas.companion_surface_ws import SurfaceAttentionStateIn, SurfaceHardwareCommand
from backend.websocket.connection_manager import ConnectionManager, PromptItem


@dataclass(eq=False)
class _Socket:
    accepted_subprotocol: str | None = None
    sent: list[dict[str, Any]] = field(default_factory=list)

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted_subprotocol = subprotocol

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [p for p in self.sent if p.get("type") == kind]


@dataclass(eq=False)
class _AudioSession:
    conversation_session_id: int | None = None
    prompts: list[PromptItem] = field(default_factory=list)

    async def release_voice_instruction(self, owner: str) -> bool:
        return False

    def enqueue_prompt(self, item: PromptItem) -> None:
        self.prompts.append(item)


def _command(surface_id: str, **overrides: Any) -> SurfaceHardwareCommand:
    values: dict[str, Any] = {
        "surface_id": surface_id,
        "lease_owner": "guided_task_start:12",
        "reason": "guided_task_start",
        "wake_screen": True,
        "enable_microphone": True,
        "enable_camera": True,
        "lease_seconds": 120,
        "server_timestamp": datetime(2026, 11, 24, 9, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return SurfaceHardwareCommand(**values)


async def _two_rooms() -> tuple[ConnectionManager, _Socket, _Socket]:
    manager = ConnectionManager()
    kitchen, bedroom = _Socket(), _Socket()
    await manager.connect(kitchen, surface_id="kitchen-tablet")  # type: ignore[arg-type]
    await manager.connect(bedroom, surface_id="bedroom-tablet")  # type: ignore[arg-type]
    return manager, kitchen, bedroom


@pytest.mark.asyncio
async def test_ws_manager_routes_hardware_command_and_prompt_only_to_matching_surface_id() -> None:
    manager, kitchen, bedroom = await _two_rooms()
    kitchen_session, bedroom_session = _AudioSession(), _AudioSession()
    manager.register_audio_handler(kitchen_session, surface_id="kitchen-tablet")
    manager.register_audio_handler(bedroom_session, surface_id="bedroom-tablet")

    reached = await manager.send_hardware_command(_command("kitchen-tablet"))
    await manager.send_backend_task("Fill the kettle.", surface_id="kitchen-tablet")
    await manager.send_to_surface("kitchen-tablet", {"type": "enable_microphone"})

    assert reached == 1
    assert kitchen.of_type("surface_hardware_command")[0]["enable_microphone"] is True
    assert kitchen.of_type("enable_microphone")
    assert [p[0] for p in kitchen_session.prompts] == ["Fill the kettle."]
    assert bedroom.sent == []
    assert bedroom_session.prompts == []
    assert manager.prompt_queue.empty()


@pytest.mark.asyncio
async def test_ws_manager_falls_back_to_broadcast_when_target_surface_offline() -> None:
    manager, kitchen, bedroom = await _two_rooms()
    shared = _AudioSession()
    manager.register_audio_handler(shared)

    await manager.send_to_surface("hallway-tablet", {"type": "guided_session_state"})
    await manager.send_backend_task("Fill the kettle.", surface_id="hallway-tablet")

    # Resident-safe content still reaches her on another screen...
    assert kitchen.of_type("guided_session_state")
    assert bedroom.of_type("guided_session_state")
    # ...and the prompt waits on the shared queue for whichever session is free.
    assert shared.prompts == []
    assert manager.prompt_queue.qsize() == 1
    assert manager.reaches_surface("hallway-tablet") is True


@pytest.mark.asyncio
async def test_hardware_command_never_falls_back_to_other_rooms() -> None:
    manager, kitchen, bedroom = await _two_rooms()

    reached = await manager.send_hardware_command(_command("hallway-tablet"))

    assert reached == 0
    assert kitchen.sent == []
    assert bedroom.sent == []


@pytest.mark.asyncio
async def test_a_surfaceless_connection_only_receives_house_wide_messages() -> None:
    manager = ConnectionManager()
    browser = _Socket()
    await manager.connect(browser)  # type: ignore[arg-type]

    assert await manager.send_hardware_command(_command("kitchen-tablet")) == 0
    await manager.send_to_surface(None, {"type": "info_card"})

    assert [p["type"] for p in browser.sent] == ["info_card"]
    assert manager.is_surface_connected("kitchen-tablet") is False
    assert manager.reaches_surface("kitchen-tablet") is True


@pytest.mark.asyncio
async def test_disconnect_forgets_the_surface_and_its_attention() -> None:
    manager, kitchen, _ = await _two_rooms()
    manager.record_attention(
        "kitchen-tablet", SurfaceAttentionStateIn(type="surface_attention_state", face_present=True)
    )
    assert manager.latest_attention("kitchen-tablet") is not None

    await manager.disconnect(kitchen)  # type: ignore[arg-type]

    assert manager.is_surface_connected("kitchen-tablet") is False
    assert manager.latest_attention("kitchen-tablet") is None
    assert await manager.send_hardware_command(_command("kitchen-tablet")) == 0


@pytest.mark.asyncio
async def test_conversation_is_resolved_per_surface() -> None:
    manager = ConnectionManager()
    manager.register_audio_handler(_AudioSession(conversation_session_id=7), surface_id="kitchen")
    manager.register_audio_handler(_AudioSession(conversation_session_id=9), surface_id="bedroom")

    assert manager.conversation_session_id("kitchen") == 7
    assert manager.conversation_session_id("bedroom") == 9
    # Unknown surface: the newest session's conversation, as an untargeted prompt would.
    assert manager.conversation_session_id("hallway") == 9


@pytest.mark.asyncio
async def test_a_reconnected_surface_takes_its_prompts_on_the_newest_session() -> None:
    manager = ConnectionManager()
    old, new = _AudioSession(), _AudioSession()
    manager.register_audio_handler(old, surface_id="kitchen-tablet")
    manager.register_audio_handler(new, surface_id="kitchen-tablet")

    await manager.send_backend_task("Step two.", surface_id="kitchen-tablet")

    assert old.prompts == []
    assert [p[0] for p in new.prompts] == ["Step two."]


def test_attention_reading_rejects_an_image() -> None:
    """Only face presence and head angles may leave the tablet: no image or embedding."""
    with pytest.raises(ValueError, match="snapshot_base64"):
        SurfaceAttentionStateIn.model_validate(
            {"type": "surface_attention_state", "face_present": True, "snapshot_base64": "AAAA"}
        )
