from __future__ import annotations

from typing import Any

import pytest

from backend.services.interactive_session import inject_session_prompt


class _FakeConnectionManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_backend_task(
        self,
        *,
        prompt: str,
        callback: Any = None,
        voice_instruction: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append(
            {
                "prompt": prompt,
                "callback": callback,
                "voice_instruction": voice_instruction,
                "metadata": metadata,
            }
        )


@pytest.mark.asyncio
async def test_inject_session_prompt_builds_metadata() -> None:
    ws_manager = _FakeConnectionManager()

    await inject_session_prompt(
        ws_manager,
        prompt="Start",
        delivery_type="quiz_start",
        session_id=7,
        execution_id=42,
        voice_instruction="Speak gently",
    )

    assert ws_manager.calls == [
        {
            "prompt": "Start",
            "callback": None,
            "voice_instruction": "Speak gently",
            "metadata": {
                "delivery_type": "quiz_start",
                "session_id": 7,
                "execution_id": 42,
            },
        }
    ]


@pytest.mark.asyncio
async def test_inject_session_prompt_without_execution_id_omits_key() -> None:
    ws_manager = _FakeConnectionManager()

    await inject_session_prompt(
        ws_manager,
        prompt="Start",
        delivery_type="quiz_start",
        session_id=7,
    )

    assert ws_manager.calls[0]["metadata"] == {
        "delivery_type": "quiz_start",
        "session_id": 7,
    }


@pytest.mark.asyncio
async def test_inject_session_prompt_merges_extra_metadata() -> None:
    ws_manager = _FakeConnectionManager()

    await inject_session_prompt(
        ws_manager,
        prompt="Start",
        delivery_type="quiz_start",
        session_id=7,
        execution_id=42,
        extra_metadata={
            "delivery_type": "wrong",
            "session_id": 999,
            "execution_id": 999,
            "quiz_id": 3,
        },
    )

    assert ws_manager.calls[0]["metadata"] == {
        "delivery_type": "quiz_start",
        "session_id": 7,
        "execution_id": 42,
        "quiz_id": 3,
    }
