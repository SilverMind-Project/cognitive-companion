"""
Ollama LLM provider implementing :class:`LLMProvider`.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.core.logging import get_logger
from backend.integrations.llm.base import LLMProvider

logger = get_logger(__name__)

_DEFAULT_TIMEOUT = 120.0  # seconds


class OllamaProvider(LLMProvider):
    """
    Talks to a local (or remote) Ollama instance via its ``/api/chat``
    endpoint.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        max_tokens: int = 4096,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout

    # -- LLMProvider interface ------------------------------------------------

    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
        response_schema: dict | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send *prompt* to Ollama and return the assistant's reply.

        When *response_schema* is a JSON Schema dict, it is passed directly
        to the ``format`` field so Ollama's guided decoding guarantees the
        output conforms to the schema. Otherwise generic JSON mode is used.

        ``media_paths`` and ``media_type`` are accepted for interface
        compatibility but are currently unused.
        """
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        # Use schema-enforced output when a schema is provided,
        # otherwise fall back to generic JSON mode.
        format_value: str | dict = response_schema if response_schema else "json"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "format": format_value,
            "stream": False,
            "options": {
                "temperature": 0.9,
                "num_predict": self.max_tokens,
            },
        }

        logger.info("ollama_request", model=self.model)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        text: str = data["message"]["content"]
        logger.debug("ollama_response", length=len(text))
        return text
