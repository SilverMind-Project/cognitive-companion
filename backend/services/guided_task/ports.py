"""Guided-task side-effect ports and no-op defaults."""

from __future__ import annotations

from typing import Any, Protocol

from backend.core.logging import get_logger

logger = get_logger(__name__)


class SessionVoice(Protocol):
    async def speak_step(
        self,
        *,
        session: Any,
        step: Any,
        rendered_prompt: str,
        is_retry: bool,
    ) -> None: ...


class SafetyWatch(Protocol):
    async def evaluate(self, *, session: Any) -> list[dict]: ...


class Escalator(Protocol):
    async def escalate(self, *, session: Any, reason: str, emergency: bool) -> None: ...


class NoopSessionVoice:
    async def speak_step(
        self,
        *,
        session: Any,
        step: Any,
        rendered_prompt: str,
        is_retry: bool,
    ) -> None:
        logger.info(
            "guided_voice_noop",
            session_id=session.id,
            step_ord=step.ord,
            is_retry=is_retry,
        )


class NoopSafetyWatch:
    async def evaluate(self, *, session: Any) -> list[dict]:
        return []


class NoopEscalator:
    async def escalate(self, *, session: Any, reason: str, emergency: bool) -> None:
        logger.info(
            "guided_escalation_noop",
            session_id=session.id,
            reason=reason,
            emergency=emergency,
        )
