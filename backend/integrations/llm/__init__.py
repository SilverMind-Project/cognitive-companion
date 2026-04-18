"""
LLM provider abstraction layer.

Supports single providers, fallback chains, load-balanced pools, and a
named model registry driven by ``llm.models`` in settings.yaml.

Usage::

    from backend.integrations.llm import get_provider, LLMModelRegistry

    # Legacy: single provider from settings section
    provider = get_provider("ollama")

    # Registry: look up a named model configured in llm.models
    registry = LLMModelRegistry()
    registry.load_from_settings()
    provider = registry.get_provider("gemma4_26b")
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.integrations.llm.base import (
    LLMProvider,
    RealtimeLLMProvider,
    RealtimeSession,
)

__all__ = [
    "LLMModelConfig",
    "LLMModelRegistry",
    "LLMProvider",
    "RealtimeLLMProvider",
    "RealtimeSession",
    "get_llm_provider",
    "get_provider",
]

# ---------------------------------------------------------------------------
# Legacy provider map (used by get_provider / get_llm_provider)
# ---------------------------------------------------------------------------

# Provider type string -> (module path, class name)
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "ollama": (
        "backend.integrations.llm.ollama",
        "OllamaProvider",
    ),
    "openai_compat": (
        "backend.integrations.llm.openai_compat",
        "OpenAICompatibleProvider",
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
        raise ValueError(f"Unknown LLM provider type {provider_type!r}. Available: {available}")

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
     "ollama": "llm.logic",
}


def _build_provider_from_config(section: dict) -> LLMProvider:
    """Build a single provider from a config section dict."""
    provider_type = section.get("provider", "")
    config: dict = {}
    for key, value in section.items():
        if key in (
            "provider",
            "primary",
            "fallback",
            "providers",
            "strategy",
            "timeout_seconds",
            "retry_count",
        ):
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
          logic:
            provider: ollama
            url: http://...
            model: llava:7b

    2. **Chain** (fallback) -- tries primary, falls back to secondary::

        llm:
          logic:
            primary:
              provider: ollama
              url: ...
            fallback:
              provider: openai_compat
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
        raise ValueError(f"Unknown LLM provider type {provider_type!r}. Available: {available}")

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


# ---------------------------------------------------------------------------
# Named model registry (used by the unified llm_call step)
# ---------------------------------------------------------------------------


@dataclass
class LLMModelConfig:
    """Static configuration for a named LLM model entry in settings.yaml."""

    id: str
    name: str
    api_type: str  # "openai" | "ollama"
    base_url: str
    model: str
    capabilities: list[str] = field(default_factory=lambda: ["text"])
    max_tokens: int = 4096
    timeout: float = 60.0
    guided_decoding: bool = False  # vLLM-style guided_json enforcement
    max_retries: int = 3
    supports_thinking: bool = False  # model honours <think>…</think> format
    temperature: float | None = None  # None = use server default
    top_p: float | None = None  # None = use server default


class LLMModelRegistry:
    """
    Registry of named LLM models loaded from ``llm.models`` in settings.yaml.

    Each model entry exposes a lazy-constructed :class:`LLMProvider` instance.
    Instances are cached after first use.

    Example ``settings.yaml``::

        llm:
          models:
            - id: cosmos_reason2
              name: "Cosmos Reason2 8B (Vision)"
              api_type: openai
              base_url: "${VISION_MODEL_URL}"
              model: "nvidia/Cosmos-Reason2-8B"
              capabilities: [text, vision]
              max_tokens: 4096
              timeout: 120
              guided_decoding: true

            - id: gemma4_26b
              name: "Gemma 4 26B (General)"
              api_type: openai
              base_url: "http://192.168.1.31:8100"
              model: "gemma-4-26B-A4B-it-GGUF"
              capabilities: [text, vision, translation]
              max_tokens: 4096
              timeout: 60
              guided_decoding: false

            - id: gemma3_4b
              name: "Gemma 3 4B (Logic)"
              api_type: ollama
              base_url: "${LOGIC_MODEL_URL}"
              model: "gemma3:4b"
              capabilities: [text]
    """

    def __init__(self) -> None:
        self._configs: dict[str, LLMModelConfig] = {}
        self._instances: dict[str, LLMProvider] = {}

    def load_from_settings(self) -> None:
        """Parse ``llm.models`` from application settings and populate the registry."""
        from backend.core.config import settings

        models_raw: list[dict] = settings.get("llm.models") or []
        for entry in models_raw:
            model_id = entry.get("id")
            if not model_id:
                continue
            raw_temperature = entry.get("temperature")
            raw_top_p = entry.get("top_p")
            cfg = LLMModelConfig(
                id=model_id,
                name=entry.get("name", model_id),
                api_type=entry.get("api_type", "openai"),
                base_url=entry.get("base_url", ""),
                model=entry.get("model", ""),
                capabilities=list(entry.get("capabilities", ["text"])),
                max_tokens=int(entry.get("max_tokens", 4096)),
                timeout=float(entry.get("timeout", 60)),
                guided_decoding=bool(entry.get("guided_decoding", False)),
                max_retries=int(entry.get("max_retries", 3)),
                supports_thinking=bool(entry.get("supports_thinking", False)),
                temperature=float(raw_temperature) if raw_temperature is not None else None,
                top_p=float(raw_top_p) if raw_top_p is not None else None,
            )
            self._configs[model_id] = cfg

    def get_provider(self, model_id: str) -> LLMProvider | None:
        """Return a (cached) :class:`LLMProvider` for *model_id*, or ``None``."""
        if model_id not in self._configs:
            return None
        if model_id not in self._instances:
            self._instances[model_id] = self._build(self._configs[model_id])
        return self._instances[model_id]

    def get_config(self, model_id: str) -> LLMModelConfig | None:
        """Return the config for *model_id*, or ``None``."""
        return self._configs.get(model_id)

    def all_configs(self) -> list[LLMModelConfig]:
        """Return all registered model configs."""
        return list(self._configs.values())

    def _build(self, cfg: LLMModelConfig) -> LLMProvider:
        if cfg.api_type == "ollama":
            from backend.integrations.llm.ollama import OllamaProvider

            return OllamaProvider(
                base_url=cfg.base_url,
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                timeout=cfg.timeout,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
            )
        # Default: OpenAI-compatible (vLLM, llama.cpp, etc.)
        from backend.integrations.llm.openai_compat import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            base_url=cfg.base_url,
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            timeout=cfg.timeout,
            guided_decoding=cfg.guided_decoding,
            max_retries=cfg.max_retries,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
        )
