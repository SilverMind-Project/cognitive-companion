from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.guided_task.agent_voice import AgentSessionVoice
from backend.services.interactive_session.tagging import prefix_for_delivery


class _Ws:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_backend_task(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _VoiceInstructions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def compose(
        self,
        *,
        step_type: str,
        base_instruction: str,
        step_override: str | None,
        resource_override: str | None,
    ) -> str:
        self.calls.append(
            {
                "step_type": step_type,
                "base_instruction": base_instruction,
                "step_override": step_override,
                "resource_override": resource_override,
            }
        )
        return resource_override or "default guided voice"


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
    voice = _VoiceInstructions()
    speaker = AgentSessionVoice(ws, voice)

    await speaker.speak_step(
        session=_session(),
        step=SimpleNamespace(ord=2),
        rendered_prompt="Pour water.",
        is_retry=True,
    )

    assert ws.calls == [
        {
            "prompt": "Pour water.",
            "callback": None,
            "voice_instruction": "default guided voice",
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
    voice = _VoiceInstructions()
    speaker = AgentSessionVoice(ws, voice)

    await speaker.speak_step(
        session=_session(routine_system_instruction_override="Speak in Tamil."),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Start.",
        is_retry=False,
    )

    assert voice.calls[0]["resource_override"] == "Speak in Tamil."
    assert ws.calls[0]["voice_instruction"] == "Speak in Tamil."


@pytest.mark.asyncio
async def test_speak_step_renders_resident_name_in_voice_instruction() -> None:
    ws = _Ws()
    voice = _VoiceInstructions()
    speaker = AgentSessionVoice(ws, voice)

    await speaker.speak_step(
        session=_session(routine_system_instruction_override="Help {{resident_name}}."),
        step=SimpleNamespace(ord=0),
        rendered_prompt="Start.",
        is_retry=False,
    )

    assert ws.calls[0]["voice_instruction"] == "Help Ruth."


@pytest.mark.asyncio
async def test_speak_step_without_memory_service_is_graceful() -> None:
    ws = _Ws()
    voice = _VoiceInstructions()
    speaker = AgentSessionVoice(ws, voice, memory_query=None)

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
