from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.config import Settings
from backend.services.guided_task.agent_voice import AgentSessionVoice
from backend.services.interactive_session.tagging import prefix_for_delivery
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig


class _Ws:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.broadcasts: list[dict] = []
        self.released: list[str] = []

    async def send_backend_task(self, **kwargs) -> None:
        self.calls.append(kwargs)

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)

    async def release_voice_instruction(self, owner: str) -> bool:
        self.released.append(owner)
        return True


BASE = "You are the household companion."
DEFAULT = "Guide {{resident_name}} one step at a time."


def _voice() -> VoiceInstructionConfig:
    return VoiceInstructionConfig(guided_task_default=DEFAULT)


def _speaker(ws: _Ws, **kwargs) -> AgentSessionVoice:
    settings = Settings.from_dict({"llm": {"realtime": {"system_instruction": BASE}}})
    return AgentSessionVoice(ws, _voice(), settings=settings, **kwargs)


def _session(**overrides):
    values = {
        "id": 3,
        "execution_id": 42,
        "person_id": "resident-1",
        "resident_name": "Ruth",
        "routine_system_instruction_override": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_speak_step_injects_with_guided_prefix_metadata() -> None:
    ws = _Ws()
    speaker = _speaker(ws)

    await speaker.speak_step(
        session=_session(),
        step=SimpleNamespace(ord=2),
        rendered_prompt="Pour water.",
        is_retry=True,
    )

    assert ws.calls == [
        {
            "prompt": "[step_ord 2] Pour water.",
            "callback": None,
            "voice_instruction": f"{BASE}\n\nGuide Ruth one step at a time.",
            "metadata": {
                "step_ord": 2,
                "is_retry": True,
                "delivery_type": "guided_task_start",
                "session_id": 3,
                "execution_id": 42,
            },
        }
    ]


@pytest.mark.asyncio
async def test_speak_step_uses_routine_voice_override() -> None:
    ws = _Ws()
    speaker = _speaker(ws)

    await speaker.speak_step(
        session=_session(routine_system_instruction_override="Speak in Tamil."),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Start.",
        is_retry=False,
    )

    assert ws.calls[0]["voice_instruction"] == f"{BASE}\n\nSpeak in Tamil."


@pytest.mark.asyncio
async def test_speak_step_renders_resident_name_in_voice_instruction() -> None:
    ws = _Ws()
    speaker = _speaker(ws)

    await speaker.speak_step(
        session=_session(routine_system_instruction_override="Help {{resident_name}}."),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Start.",
        is_retry=False,
    )

    assert ws.calls[0]["voice_instruction"] == f"{BASE}\n\nHelp Ruth."


@pytest.mark.asyncio
async def test_speak_step_without_memory_service_is_graceful() -> None:
    ws = _Ws()
    speaker = _speaker(ws, memory_query=None)

    await speaker.speak_step(
        session=_session(),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Start.",
        is_retry=False,
    )

    assert len(ws.calls) == 1


def test_guided_prefix_registered() -> None:
    assert (
        prefix_for_delivery({"delivery_type": "guided_task_start", "session_id": 3})
        == "[guided task session 3]"
    )


@pytest.mark.asyncio
async def test_speak_step_turns_the_tablet_microphone_on_first() -> None:
    """She answers aloud; an idle tablet with its microphone off would hear nothing."""
    order: list[str] = []
    ws = _Ws()

    async def broadcast(payload: dict) -> None:
        order.append(payload["type"])
        ws.broadcasts.append(payload)

    async def send_backend_task(**kwargs) -> None:
        order.append("prompt")

    ws.broadcast = broadcast  # type: ignore[method-assign]
    ws.send_backend_task = send_backend_task  # type: ignore[method-assign]

    await _speaker(ws).speak_step(
        session=_session(),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Pour water.",
        is_retry=False,
    )

    assert order == ["enable_microphone", "prompt"]
    assert ws.broadcasts[0] == {
        "type": "enable_microphone",
        "reason": "guided_task",
        "session_id": 3,
    }


@pytest.mark.asyncio
async def test_spoken_step_carries_its_step_ord_and_total() -> None:
    """The agent must not infer the step from its wording ("step 1" is step_ord 0)."""
    ws = _Ws()

    await _speaker(ws).speak_step(
        session=_session(total_steps=3),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Say only these words: test step 1.",
        is_retry=False,
    )

    assert ws.calls[0]["prompt"] == "[step_ord 0 of 3] Say only these words: test step 1."
