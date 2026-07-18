"""Resident-language resolution shared by the agent voice path and the service.

Design principle (D15): the agent translates, code does not. This module only
resolves *which* language to direct the agent toward and renders the small
instruction templates that carry that direction; it never translates
resident-facing prose itself.
"""

from __future__ import annotations

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

logger = get_logger(__name__)

_DEFAULT_LANGUAGE_DIRECTIVE = "For this routine, speak only in {{ language }}."


def resolve_language_name(settings: Settings, code: str) -> str:
    """Map a language code to its display name via ``app.language_names``.

    An unmapped code passes through verbatim (degrade, not a crash) with a
    warning so a missing mapping is visible instead of silently mistranslated.
    """
    names = settings.get("app.language_names", {}) or {}
    name = names.get(code)
    if name is None:
        logger.warning("guided_language_name_unknown", code=code)
        return code
    return name


def compose_language_directive(
    settings: Settings,
    voice_config: VoiceInstructionConfig,
    language_override: str | None,
) -> str | None:
    """Render the agent-facing language directive for a routine override.

    Returns ``None`` when no override is set, so callers can skip appending
    anything to the composed instruction.
    """
    if not language_override:
        return None
    template = voice_config.guided_task_language_directive or _DEFAULT_LANGUAGE_DIRECTIVE
    language_name = resolve_language_name(settings, language_override)
    return render_template(template, {"language": language_name})
