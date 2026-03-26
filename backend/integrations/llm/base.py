"""
Abstract base classes for LLM providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


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

        Returns
        -------
        str
            The model's text completion.
        """
        ...


class RealtimeLLMProvider(ABC):
    """Base class for streaming / real-time LLM providers (e.g. voice)."""

    @abstractmethod
    async def connect(self, config: dict[str, Any]) -> RealtimeSession:
        """Open a persistent session with the provider."""
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
            yield  # type: ignore[misc]

    @abstractmethod
    async def disconnect(self, session: RealtimeSession) -> None:
        """Gracefully tear down the session."""
        ...
