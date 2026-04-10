"""
Configuration loader — reads YAML files with ``${ENV_VAR}`` interpolation.

Architecture
------------
This module exposes two things:

* :class:`Settings` — a pure, injectable configuration container. It has no
  module-level state and can be instantiated freely in tests with either a
  custom ``config_dir`` or a raw dict via :meth:`Settings.from_dict`.
* ``settings`` — a module-level :class:`Settings` instance that serves as the
  application's lazily-loaded singleton. Application code continues to import
  and use ``settings`` exactly as before.

The split lets tests create fresh, isolated ``Settings`` objects without
touching process global state, while the public import surface
(``from backend.core.config import settings``) remains unchanged.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from backend.core.logging import get_logger

__all__ = ["DEFAULT_CONFIG_DIR", "Settings", "settings"]

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")
DEFAULT_CONFIG_DIR: Path = Path(__file__).resolve().parents[2] / "config"

_CONFIG_FILES: tuple[tuple[str, str | None], ...] = (
    # (filename, namespace) — namespace=None means merge at top level.
    ("settings.yaml", None),
    ("auth.yaml", "auth"),
    ("notifications.yaml", "notifications"),
)

logger = get_logger(__name__)


def _interpolate(value: Any, env: Mapping[str, str]) -> Any:
    """Recursively replace ``${ENV_VAR}`` placeholders with values from *env*.

    A missing variable becomes an empty string, matching shell behavior and
    the previous implementation.
    """
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: env.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _interpolate(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, env) for v in value]
    return value


def _load_yaml_file(path: Path, env: Mapping[str, str]) -> dict:
    """Read a YAML file and apply env interpolation.

    Returns an empty dict if the file is missing (logged as a warning) or if
    the file parses to ``None`` (empty file).
    """
    if not path.exists():
        logger.warning("config_file_missing", path=str(path))
        return {}
    logger.info("config_file_loading", path=str(path))
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return _interpolate(raw, env)


class Settings:
    """Lazily loaded, dict-like settings backed by YAML files plus env vars.

    Instances are cheap to construct and fully isolated. Tests should prefer
    :meth:`from_dict` to skip disk I/O entirely::

        s = Settings.from_dict({"llm": {"model": "fake"}})
        assert s.get("llm.model") == "fake"
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._config_dir: Path = config_dir or DEFAULT_CONFIG_DIR
        self._env: Mapping[str, str] = env if env is not None else os.environ
        self._data: dict = {}
        self._loaded: bool = False

    # -- construction helpers -------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Settings:
        """Build a Settings object directly from an in-memory mapping.

        The resulting instance is marked as already loaded, so accessing keys
        will never touch the filesystem. Intended primarily for tests.
        """
        inst = cls.__new__(cls)
        inst._config_dir = DEFAULT_CONFIG_DIR
        inst._env = os.environ
        inst._data = dict(data)
        inst._loaded = True
        return inst

    # -- public API -----------------------------------------------------------

    @property
    def config_dir(self) -> Path:
        """The directory this Settings instance reads YAML files from."""
        return self._config_dir

    def reload(self, config_dir: Path | None = None) -> None:
        """(Re-)load all config files from *config_dir* or the current one."""
        if config_dir is not None:
            self._config_dir = config_dir
        merged: dict[str, Any] = {}
        for filename, namespace in _CONFIG_FILES:
            loaded = _load_yaml_file(self._config_dir / filename, self._env)
            if namespace is None:
                merged.update(loaded)
            else:
                merged[namespace] = loaded
        self._data = merged
        self._loaded = True

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Retrieve a nested value using dot notation.

        >>> settings.get("llm.vision.model")
        'nvidia/Cosmos-Reason2-8B'

        Returns *default* if any segment of the path is missing or traverses
        through a non-dict value.
        """
        self._ensure_loaded()
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict):
                return default
            node = node.get(part)
            if node is None:
                return default
        return node

    def raw(self) -> dict:
        """Return the full merged config dict (for debugging / admin endpoint)."""
        self._ensure_loaded()
        return self._data

    # -- dunder sugar ---------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    # -- internal -------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()


#: Process-wide settings singleton. Imported throughout the backend as
#: ``from backend.core.config import settings``.
settings: Settings = Settings()
