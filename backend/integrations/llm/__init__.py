"""
LLM provider abstraction layer.

Supports single providers, fallback chains, and load-balanced pools.

Usage::

    from backend.integrations.llm import get_provider

    # Single provider (from settings)
    provider = get_provider("vllm_vision")

    # Chain/pool configured in settings.yaml
    result = await provider.call("Describe this image.", media_paths=["photo.jpg"])
"""

from __future__ import annotations

from backend.integrations.llm.base import (
    LLMProvider,
    RealtimeLLMProvider,
    RealtimeSession,
)

__all__ = [
    "LLMProvider",
    "RealtimeLLMProvider",
    "RealtimeSession",
    "get_llm_provider",
    "get_provider",
]

# Provider type string -> (module path, class name)
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "vllm_vision": (
        "backend.integrations.llm.vllm",
        "VLLMVisionProvider",
    ),
    "vllm_translation": (
        "backend.integrations.llm.vllm",
        "VLLMTranslationProvider",
    ),
    "ollama": (
        "backend.integrations.llm.ollama",
        "OllamaProvider",
    ),
}


def get_llm_provider(provider_type: str, config: dict) -> LLMProvider:
    """
    Factory that returns an :class:`LLMProvider` instance based on
    *provider_type*.
    """
    entry = _PROVIDER_MAP.get(provider_type)
    if entry is None:
        available = ", ".join(sorted(_PROVIDER_MAP))
        raise ValueError(
            f"Unknown LLM provider type {provider_type!r}. "
            f"Available: {available}"
        )

    module_path, class_name = entry

    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**config)


def register_provider(provider_type: str, module_path: str, class_name: str) -> None:
    """Register a new LLM provider type at runtime."""
    _PROVIDER_MAP[provider_type] = (module_path, class_name)


# Maps settings YAML provider type -> config section dotted key
_SETTINGS_SECTION: dict[str, str] = {
    "vllm_vision": "llm.vision",
    "vllm_translation": "llm.translation",
    "ollama": "llm.logic",
}


def _build_provider_from_config(section: dict) -> LLMProvider:
    """Build a single provider from a config section dict."""
    provider_type = section.get("provider", "")
    config: dict = {}
    for key, value in section.items():
        if key in ("provider", "primary", "fallback", "providers", "strategy",
                    "timeout_seconds", "retry_count"):
            continue
        if key == "url":
            config["base_url"] = value
        else:
            config[key] = value
    return get_llm_provider(provider_type, config)


def get_provider(provider_type: str) -> LLMProvider:
    """Create an :class:`LLMProvider` from a *provider_type* string,
    automatically pulling constructor kwargs from the application settings.

    Supports three configurations:

    1. **Simple** -- single provider::

        llm:
          vision:
            provider: vllm_vision
            url: http://...
            model: nvidia/Cosmos-Reason2-8B

    2. **Chain** (fallback) -- tries primary, falls back to secondary::

        llm:
          vision:
            primary:
              provider: vllm_vision
              url: ...
            fallback:
              provider: ollama
              url: ...
            retry_count: 2

    3. **Pool** (load balancing) -- round-robin across providers::

        llm:
          logic:
            strategy: round_robin
            providers:
              - provider: ollama
                url: http://gpu-node-1:11434
              - provider: ollama
                url: http://gpu-node-2:11434
    """
    from backend.core.config import settings

    section_key = _SETTINGS_SECTION.get(provider_type)
    if section_key is None:
        available = ", ".join(sorted(_SETTINGS_SECTION))
        raise ValueError(
            f"Unknown LLM provider type {provider_type!r}. "
            f"Available: {available}"
        )

    section: dict = settings.get(section_key) or {}

    # Pool mode
    if "providers" in section and isinstance(section["providers"], list):
        from backend.integrations.llm.chain import LLMProviderPool

        providers = [_build_provider_from_config(p) for p in section["providers"]]
        strategy = section.get("strategy", "round_robin")
        return LLMProviderPool(providers=providers, strategy=strategy)

    # Chain mode (primary + fallback)
    if "primary" in section and isinstance(section["primary"], dict):
        from backend.integrations.llm.chain import LLMProviderChain

        primary = _build_provider_from_config(section["primary"])
        chain_providers = [primary]
        if "fallback" in section and isinstance(section["fallback"], dict):
            fallback = _build_provider_from_config(section["fallback"])
            chain_providers.append(fallback)
        retry_count = section.get("retry_count", 2)
        return LLMProviderChain(providers=chain_providers, retry_count=retry_count)

    # Simple mode
    config: dict = {}
    for key, value in section.items():
        if key == "provider":
            continue
        if key == "url":
            config["base_url"] = value
        else:
            config[key] = value

    return get_llm_provider(provider_type, config)
