"""Voice instruction config loaded from config/knowledge_voice.yaml.

Frozen dataclass with defaults for each delivery type. Loaded at startup
and attached to app.state.voice_instructions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from backend.core.logging import get_logger
from backend.core.template import render_template

logger = get_logger(__name__)

QuizInteractionMode = Literal["gentle", "standard"]
QUIZ_INTERACTION_MODES: tuple[QuizInteractionMode, ...] = ("gentle", "standard")


@dataclass(frozen=True, slots=True)
class VoiceInstructionConfig:
    """Default voice instructions for Gemini Live during knowledge delivery."""

    interactive_prompt_default: str = ""
    info_card_default: str = ""
    quiz_default: str = ""
    quiz_gentle_directive: str = ""
    quiz_standard_directive: str = ""
    guided_task_default: str = ""
    guided_task_language_directive: str = ""
    guided_task_auto_advance_prefix: str = ""

    @classmethod
    def load(cls, path: str | Path) -> VoiceInstructionConfig:
        path = Path(path)
        if not path.is_absolute():
            candidate = Path.cwd().parent / path
            if candidate.exists():
                path = candidate

        if not path.exists():
            logger.warning("voice_config_not_found", path=str(path))
            return cls()

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        config = cls(
            interactive_prompt_default=raw.get("interactive_prompt_default", "").strip(),
            info_card_default=raw.get("info_card_default", "").strip(),
            quiz_default=raw.get("quiz_default", "").strip(),
            quiz_gentle_directive=raw.get("quiz_gentle_directive", "").strip(),
            quiz_standard_directive=raw.get("quiz_standard_directive", "").strip(),
            guided_task_default=raw.get("guided_task_default", "").strip(),
            guided_task_language_directive=raw.get("guided_task_language_directive", "").strip(),
            guided_task_auto_advance_prefix=raw.get("guided_task_auto_advance_prefix", "").strip(),
        )
        logger.info("voice_instructions_loaded", path=str(path))
        return config

    def default_for(self, step_type: str) -> str:
        """Return the default voice instruction for a given step or resource type."""
        key = f"{step_type}_default"
        return getattr(self, key, "")

    def quiz_mode_directive(self, mode: QuizInteractionMode) -> str:
        """The feedback rules for a quiz interaction mode.

        Appended after any caregiver override, so a custom quiz persona can change the
        tone but never turns gentle (errorless learning) mode into graded testing.
        """
        return self.quiz_gentle_directive if mode == "gentle" else self.quiz_standard_directive

    def compose(
        self,
        step_type: str,
        base_instruction: str,
        step_override: str | None = None,
        resource_override: str | None = None,
        *,
        context: Mapping[str, Any] | None = None,
        directive: str = "",
    ) -> str:
        """Compose the effective system instruction per the unified rule.

        The base instruction (the companion's persona, household context, and tool
        rules) always comes first; a delivery adds to it and never replaces it.
        Resolution order for the per-delivery part: step_override > resource_override >
        voice_default. ``context`` renders ``{{ }}`` templates in that part only, and
        ``directive`` is appended last.
        """
        if step_override:
            per_delivery = step_override
        elif resource_override:
            per_delivery = resource_override
        else:
            per_delivery = self.default_for(step_type)
        if per_delivery and context is not None:
            per_delivery = render_template(per_delivery, context)

        parts = [p for p in [base_instruction, per_delivery, directive] if p]
        return "\n\n".join(parts)
