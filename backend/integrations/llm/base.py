"""
Abstract base classes for LLM providers.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Shared chain-of-thought helpers
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

THINKING_INSTRUCTION = (
    "Answer the question using the following format:\n"
    "<think>\nYour reasoning.\n</think>\n\n"
    "Write your final answer immediately after the </think> tag."
)


def strip_thinking(text: str) -> str:
    """Remove ``<think>…</think>`` reasoning blocks from model output."""
    return _THINK_RE.sub("", text).strip()


@dataclass
class RealtimeSession:
    """Holds a provider-specific session object and associated metadata."""

    session_object: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Base class for standard (request/response) LLM providers."""

    @abstractmethod
    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
        response_schema: dict | None = None,
        thinking: bool = False,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a prompt (and optional media) to the LLM and return the text
        response.

        Parameters
        ----------
        prompt:
            The user/system prompt text.
        media_paths:
            Optional list of file paths (images or video) to include.
        media_type:
            One of ``"image"``, ``"video"``, or ``None``.
        response_schema:
            Optional JSON Schema dict. When provided, the LLM is
            constrained to produce output conforming to this schema
            (via guided decoding on Ollama/vLLM).
        thinking:
            When ``True``, the provider injects a chain-of-thought instruction
            asking the model to reason inside ``<think>…</think>`` tags before
            its final answer.  The ``<think>`` block is stripped from the
            returned string; only the final answer is returned.  Providers that
            do not support this mode ignore the flag.
        temperature:
            Sampling temperature override. ``None`` uses the provider default.
        top_p:
            Top-p (nucleus) sampling override. ``None`` uses the provider default.
        max_tokens:
            Maximum tokens to generate override. ``None`` uses the provider default.

        Returns
        -------
        str
            The model's text completion (reasoning block stripped when
            ``thinking=True``).
        """
        ...


class RealtimeLLMProvider(ABC):
    """Base class for streaming / real-time LLM providers (e.g. voice)."""

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> RealtimeSession:
        """Open a persistent session with the provider."""
        ...

    @abstractmethod
    def build_config(self, **kwargs: Any) -> dict[str, Any]:
        """Build provider configuration."""
        ...

    @abstractmethod
    async def send_audio(self, session: RealtimeSession, data: bytes) -> None:
        """Stream raw audio bytes into an open session."""
        ...

    @abstractmethod
    async def send_text(self, session: RealtimeSession, text: str) -> None:
        """Send a text message into an open session."""
        ...

    @abstractmethod
    async def receive(self, session: RealtimeSession) -> AsyncIterator[Any]:
        """
        Yield events/messages from the provider as they arrive.

        The concrete type of yielded items is provider-specific.
        """
        ...  # pragma: no cover
        # Mypy/pyright need a yield to recognise this as an async generator.
        # The yield is unreachable but keeps type-checkers happy.
        if False:
            yield

    @abstractmethod
    async def send_tool_response(
        self, session: RealtimeSession, function_responses: list[Any]
    ) -> None:
        """Send tool execution results back to the provider."""
        ...

    @abstractmethod
    async def disconnect(self, session: RealtimeSession) -> None:
        """Gracefully tear down the session."""
        ...
