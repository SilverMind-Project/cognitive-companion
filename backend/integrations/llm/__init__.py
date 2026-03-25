"""
LLM provider abstraction layer.

Usage::

    from backend.integrations.llm import get_llm_provider

    provider = get_llm_provider("vllm_vision", {
        "base_url": "http://localhost:8000",
        "model": "nvidia/Cosmos-Reason2-8B",
        "max_tokens": 4096,
    })
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

    Parameters
    ----------
    provider_type:
        One of ``"vllm_vision"``, ``"vllm_translation"``, or ``"ollama"``.
    config:
        Keyword arguments forwarded to the provider's constructor
        (e.g. ``base_url``, ``model``, ``max_tokens``).

    Raises
    ------
    ValueError
        If *provider_type* is not recognised.
    """
    entry = _PROVIDER_MAP.get(provider_type)
    if entry is None:
        available = ", ".join(sorted(_PROVIDER_MAP))
        raise ValueError(
            f"Unknown LLM provider type {provider_type!r}. "
            f"Available: {available}"
        )

    module_path, class_name = entry

    # Lazy import so we only pull in dependencies that are actually needed.
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**config)
