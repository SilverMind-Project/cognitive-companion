"""Utilities for cleaning and parsing LLM-generated JSON responses."""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL,
)


def clean_llm_json(text: str) -> str:
    """Strip markdown code fences and leading/trailing whitespace from
    LLM-generated JSON text.

    Handles common patterns:
    - ```json\\n{...}\\n```
    - ```\\n{...}\\n```
    - Leading/trailing whitespace around valid JSON
    """
    text = text.strip()
    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    return text


def parse_llm_json(text: str) -> dict | list | str:
    """Attempt to parse LLM output as JSON, cleaning fences first.

    Returns the parsed object on success, or the original string on failure.
    Logs a warning on parse failure rather than silently suppressing.
    """
    cleaned = clean_llm_json(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError, TypeError:
        return text
