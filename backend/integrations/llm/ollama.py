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
        temperature: float | None = 0.9,
        top_p: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p

    # -- LLMProvider interface ------------------------------------------------

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

        effective_temperature = temperature if temperature is not None else self.temperature
        effective_top_p = top_p if top_p is not None else self.top_p
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        options: dict[str, Any] = {"num_predict": effective_max_tokens}
        if effective_temperature is not None:
            options["temperature"] = effective_temperature
        if effective_top_p is not None:
            options["top_p"] = effective_top_p

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "format": format_value,
            "stream": False,
            "options": options,
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
