"""
Google Gemini Live API - realtime audio streaming provider.

Implements RealtimeLLMProvider for bidirectional audio conversations
with automatic keepalive and context preservation across reconnects.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.llm.base import RealtimeLLMProvider, RealtimeSession

logger = get_logger(__name__)


class GeminiLiveProvider(RealtimeLLMProvider):
    """Manages a Gemini Live session for real-time audio interaction."""

    def __init__(self) -> None:
        self.api_key: str = settings.get("llm.realtime.api_key")
        self.model: str = settings.get("llm.realtime.model")
        self.keepalive_interval: int = settings.get("llm.realtime.keepalive_interval", 25)
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        """Lazy-init the genai client."""
        if self._client is None:
            from google import genai  # Lazy import: google-genai is an optional dependency
            self._client = genai.Client(
                api_key=self.api_key,
            )
        return self._client

    async def connect(self, config: dict[str, Any]) -> RealtimeSession:
        """Open a Gemini Live session with the given config."""
        client = self._get_client()
        session_manager = client.aio.live.connect(
            model=self.model,
            config=config,
        )
        session = await session_manager.__aenter__()
        return RealtimeSession(
            session_object=session,
            metadata={
                "connected_at": time.time(),
                "session_manager": session_manager,
            },
        )

    async def send_audio(self, session: RealtimeSession, data: bytes) -> None:
        """Send raw PCM audio bytes to the Gemini session."""
        from google.genai import types  # Lazy import: google-genai is an optional dependency
        logger.debug("gemini_send_audio", bytes=len(data))
        await session.session_object.send_realtime_input(
            audio=types.Blob(data=data, mime_type="audio/pcm")
        )

    async def send_text(self, session: RealtimeSession, text: str) -> None:
        """Send a text prompt into the Gemini session."""
        await session.session_object.send_realtime_input(text=text)

    async def receive(self, session: RealtimeSession) -> AsyncIterator[Any]:
        """Yield server responses from the Gemini session."""
        logger.debug("gemini_receive")
        # SDK's receive() stops after each turn_complete. Loop so the caller
        # gets a continuous stream across all turns without the backend having
        # to disconnect and reconnect between every Gemini response.
        while True:
            async for response in session.session_object.receive():
                yield response

    async def send_tool_response(
        self, session: RealtimeSession, function_responses: list
    ) -> None:
        """Send function call results back to the Gemini session."""
        logger.info("gemini_send_tool_response", count=len(function_responses))
        await session.session_object.send_tool_response(
            function_responses=function_responses,
        )

    async def disconnect(self, session: RealtimeSession) -> None:
        """Close the Gemini session."""
        session_manager = session.metadata.get("session_manager")
        try:
            if session_manager is not None:
                await session_manager.__aexit__(None, None, None)
            else:
                await session.session_object.close()
        except Exception:
            logger.debug("gemini_disconnect_error")

    def build_config(
        self,
        system_instruction: str = "",
        conversation_history: str = "",
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build the Gemini session config dict.

        If ``conversation_history`` is provided, it's appended to the system
        instruction so context survives reconnects.
        """
        base_instruction = system_instruction or settings.get(
            "llm.realtime.system_instruction", ""
        )

        if conversation_history:
            base_instruction += (
                "\n\nThis is a RESUMED conversation. Here is the transcript of "
                "what was discussed so far  use it to maintain full context "
                "and continuity:\n\n" + conversation_history
            )

        config: dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "system_instruction": {"parts": [{"text": base_instruction}]},
            "output_audio_transcription": {},
            "input_audio_transcription": {},
        }

        if tools:
            config["tools"] = [{"function_declarations": tools}]

        return config
