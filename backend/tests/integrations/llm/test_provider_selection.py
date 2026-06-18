"""Realtime provider selection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.integrations.llm.gemini_live import GeminiLiveProvider
from backend.integrations.llm.realtime import create_realtime_provider

REPO_ROOT = Path(__file__).resolve().parents[4]


def _settings(provider: str = "gemini", api_key: str = "secret") -> Settings:
    return Settings.from_dict(
        {
            "llm": {
                "realtime": {
                    "provider": provider,
                    "api_key": api_key,
                    "model": "gemini-live",
                    "keepalive_interval": 25,
                    "system_instruction": "Be concise.",
                }
            }
        }
    )


def test_default_provider_is_gemini() -> None:
    provider = create_realtime_provider(_settings())

    assert isinstance(provider, GeminiLiveProvider)


def test_unknown_provider_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown realtime LLM provider"):
        create_realtime_provider(_settings(provider="local_stt"))


def test_no_provider_created_when_api_key_missing() -> None:
    assert create_realtime_provider(_settings(api_key="")) is None


def test_no_gemini_import_outside_provider() -> None:
    offenders = []
    import_patterns = ("google" + ".genai", "from google import " + "genai")
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        if ".venv" in path.parts:
            continue
        if path == REPO_ROOT / "backend" / "integrations" / "llm" / "gemini_live.py":
            continue
        text = path.read_text()
        if any(pattern in text for pattern in import_patterns):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []
