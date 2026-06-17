"""Voice instruction config loaded from config/knowledge_voice.yaml.

Frozen dataclass with defaults for each delivery type. Loaded at startup
and attached to app.state.voice_instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class VoiceInstructionConfig:
    """Default voice instructions for Gemini Live during knowledge delivery."""

    interactive_prompt_default: str = ""
    info_card_default: str = ""
    quiz_default: str = ""
    guided_task_default: str = ""

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
            guided_task_default=raw.get("guided_task_default", "").strip(),
        )
        logger.info("voice_instructions_loaded", path=str(path))
        return config

    def default_for(self, step_type: str) -> str:
        """Return the default voice instruction for a given step or resource type."""
        key = f"{step_type}_default"
        return getattr(self, key, "")

    def compose(
        self,
        step_type: str,
        base_instruction: str,
        step_override: str | None = None,
        resource_override: str | None = None,
    ) -> str:
        """Compose the effective system instruction per the unified rule.

        Resolution order: step_override > resource_override > voice_default > base only.
        """
        # Resolve the per-delivery instruction
        per_delivery = ""
        if step_override:
            per_delivery = step_override
        elif resource_override:
            per_delivery = resource_override
        else:
            per_delivery = self.default_for(step_type)

        parts = [p for p in [base_instruction, per_delivery] if p]
        return "\n\n".join(parts)
