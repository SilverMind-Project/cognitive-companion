"""Factory for config-selected realtime LLM providers."""

from __future__ import annotations

from backend.core.config import Settings, settings
from backend.integrations.llm.base import RealtimeLLMProvider

_GEMINI_PROVIDER_KEYS = {"gemini", "gemini_live"}
_SUPPORTED_PROVIDER_KEYS = _GEMINI_PROVIDER_KEYS


def create_realtime_provider(config: Settings = settings) -> RealtimeLLMProvider | None:
    """Create the configured realtime provider, or ``None`` when unconfigured.

    The provider key is validated before optional API-key checks so startup fails
    loudly on an unknown provider instead of silently disabling voice.
    """
    provider_key = config.as_str("llm.realtime.provider", allow_empty=False).strip().lower()
    if provider_key not in _SUPPORTED_PROVIDER_KEYS:
        available = ", ".join(sorted(_SUPPORTED_PROVIDER_KEYS))
        raise ValueError(
            f"Unknown realtime LLM provider {provider_key!r}. Available providers: {available}"
        )

    realtime_api_key = config.as_str("llm.realtime.api_key")
    if not realtime_api_key:
        return None

    if provider_key in _GEMINI_PROVIDER_KEYS:
        from backend.integrations.llm.gemini_live import GeminiLiveProvider

        return GeminiLiveProvider(settings=config)

    raise AssertionError(f"Unhandled realtime LLM provider {provider_key!r}")
