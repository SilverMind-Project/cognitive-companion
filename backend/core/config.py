"""
Configuration loader - reads YAML files with ${ENV_VAR} interpolation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from backend.core.logging import get_logger

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
logger = get_logger(__name__)


def _interpolate(value: Any) -> Any:
    """Recursively replace ${ENV_VAR} placeholders with environment values."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        logger.warning("config_file_missing", path=str(path))
        return {}
    with open(path) as f:
        logger.info("config_file_loading", path=str(path))
        raw = yaml.safe_load(f) or {}
    return _interpolate(raw)


class _Settings:
    """Lazily loaded, dict-like settings backed by YAML + env vars."""

    def __init__(self) -> None:
        self._data: dict = {}
        self._loaded = False

    # -- public API -----------------------------------------------------------

    def reload(self, config_dir: Path | None = None) -> None:
        """(Re-)load all config files."""
        base = config_dir or _CONFIG_DIR
        settings = _load_yaml(base / "settings.yaml")
        auth = _load_yaml(base / "auth.yaml")
        notifications = _load_yaml(base / "notifications.yaml")
        self._data = {**settings, "auth": auth, "notifications": notifications}
        self._loaded = True

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """
        Retrieve a nested value using dot notation.

        >>> settings.get("llm.vision.model")
        'nvidia/Cosmos-Reason2-8B'
        """
        self._ensure_loaded()
        parts = dotted_key.split(".")
        node: Any = self._data
        for part in parts:
            if isinstance(node, dict):
                node = node.get(part)
            else:
                return default
            if node is None:
                return default
        return node

    def raw(self) -> dict:
        """Return the full merged config dict (for debugging / admin endpoint)."""
        self._ensure_loaded()
        return self._data

    # -- internal -------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


settings = _Settings()
