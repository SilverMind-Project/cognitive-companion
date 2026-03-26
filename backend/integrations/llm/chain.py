"""LLM provider chain (fallback) and pool (load balancing).

These wrappers compose multiple :class:`LLMProvider` instances into a single
provider that automatically handles failover or load distribution.
"""

from __future__ import annotations

import itertools

from backend.core.logging import get_logger
from backend.integrations.llm.base import LLMProvider

logger = get_logger(__name__)


class LLMProviderChain(LLMProvider):
    """Try a primary provider first, then fall back to alternatives.

    Configuration example (settings.yaml)::

        llm:
          vision:
            primary:
              provider: vllm_vision
              url: ${VISION_MODEL_URL}
              model: nvidia/Cosmos-Reason2-8B
            fallback:
              provider: ollama
              url: ${LOGIC_MODEL_URL}
              model: llava:7b
            timeout_seconds: 30
            retry_count: 2
    """

    def __init__(
        self,
        providers: list[LLMProvider],
        retry_count: int = 1,
    ) -> None:
        if not providers:
            raise ValueError("LLMProviderChain requires at least one provider")
        self._providers = providers
        self._retry_count = retry_count

    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
    ) -> str:
        last_error: Exception | None = None
        for provider in self._providers:
            for attempt in range(self._retry_count):
                try:
                    result = await provider.call(
                        prompt=prompt,
                        media_paths=media_paths,
                        media_type=media_type,
                    )
                    return result
                except Exception as e:
                    last_error = e
                    provider_name = type(provider).__name__
                    logger.warning(
                        "llm_provider_failed",
                        provider=provider_name,
                        attempt=attempt + 1,
                        error=str(e),
                    )
        raise last_error or RuntimeError("All LLM providers failed")


class LLMProviderPool(LLMProvider):
    """Distribute calls across multiple providers using round-robin.

    Configuration example (settings.yaml)::

        llm:
          logic:
            strategy: round_robin
            providers:
              - provider: ollama
                url: http://gpu-node-1:11434
                model: gemma3:4b
              - provider: ollama
                url: http://gpu-node-2:11434
                model: gemma3:4b
    """

    def __init__(
        self,
        providers: list[LLMProvider],
        strategy: str = "round_robin",
    ) -> None:
        if not providers:
            raise ValueError("LLMProviderPool requires at least one provider")
        self._providers = providers
        self._strategy = strategy
        self._cycle = itertools.cycle(range(len(providers)))

    async def call(
        self,
        prompt: str,
        media_paths: list[str] | None = None,
        media_type: str | None = None,
    ) -> str:
        idx = next(self._cycle)
        provider = self._providers[idx]
        try:
            return await provider.call(
                prompt=prompt,
                media_paths=media_paths,
                media_type=media_type,
            )
        except Exception:
            # On failure, try each remaining provider once
            for i, p in enumerate(self._providers):
                if i == idx:
                    continue
                try:
                    return await p.call(
                        prompt=prompt,
                        media_paths=media_paths,
                        media_type=media_type,
                    )
                except Exception:
                    continue
            raise
