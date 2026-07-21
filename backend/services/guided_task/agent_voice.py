"""Gemini Live voice integration for guided-task sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cachetools import TTLCache

from backend.core.config import Settings
from backend.core.config import settings as default_settings
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.services.guided_task.language import compose_language_directive
from backend.services.interactive_session.prompt_injection import inject_session_prompt
from backend.services.interactive_session.tagging import register_session_prefix

if TYPE_CHECKING:
    from backend.services.knowledge.voice_instructions import VoiceInstructionConfig
    from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)

GUIDED_TASK_DELIVERY_TYPE = "guided_task_start"

register_session_prefix(
    GUIDED_TASK_DELIVERY_TYPE,
    lambda session_id: f"[guided task session {session_id}]",
)

# Once-per-session warning budget for the unsupported voice-override degrade.
# TTL is a memory bound only (mirrors the pattern in service.py); a
# session outliving a day is not realistic for this always-on process.
_VOICE_OVERRIDE_WARNING_TTL_S = 86400


class AgentSessionVoice:
    """SessionVoice implementation that wakes the live agent with a step prompt."""

    def __init__(
        self,
        ws_manager: ConnectionManager | None,
        voice_instructions: VoiceInstructionConfig,
        memory_query: Any = None,
        settings: Settings | None = None,
    ) -> None:
        self._ws_manager = ws_manager
        self._voice = voice_instructions
        self._memory_query = memory_query
        self._settings = settings or default_settings
        self._voice_override_warned: TTLCache[int, bool] = TTLCache(
            maxsize=4096, ttl=_VOICE_OVERRIDE_WARNING_TTL_S
        )

    async def speak_step(
        self,
        *,
        session: Any,
        step: Any,
        rendered_prompt: str,
        is_retry: bool,
    ) -> None:
        if self._ws_manager is None:
            logger.warning(
                "guided_step_voice_skipped",
                session_id=session.id,
                reason="ws_manager_unavailable",
            )
            return

        voice_instruction = self._voice.compose(
            step_type="guided_task",
            base_instruction="",
            step_override=None,
            resource_override=getattr(session, "routine_system_instruction_override", None) or None,
        )
        if voice_instruction:
            voice_instruction = render_template(
                voice_instruction,
                {
                    "resident_name": getattr(session, "resident_name", ""),
                    "person_id": getattr(session, "person_id", ""),
                },
            )
        language_override = getattr(session, "language_override", None)
        directive = compose_language_directive(self._settings, self._voice, language_override)
        if directive:
            voice_instruction = (
                f"{voice_instruction}\n\n{directive}" if voice_instruction else directive
            )

        extra_metadata: dict[str, Any] = {"step_ord": step.ord, "is_retry": is_retry}
        voice_override = getattr(session, "voice_override", None)
        if voice_override:
            extra_metadata["voice"] = voice_override
            if session.id not in self._voice_override_warned:
                self._voice_override_warned[session.id] = True
                logger.warning(
                    "guided_voice_override_unsupported",
                    session_id=session.id,
                    voice_override=voice_override,
                    reason="realtime_provider_cannot_switch_voice_mid_session",
                )

        await inject_session_prompt(
            self._ws_manager,
            prompt=rendered_prompt,
            delivery_type=GUIDED_TASK_DELIVERY_TYPE,
            session_id=session.id,
            execution_id=session.execution_id,
            voice_instruction=voice_instruction or None,
            extra_metadata=extra_metadata,
        )
        logger.info(
            "guided_step_spoken",
            session_id=session.id,
            step_ord=step.ord,
            is_retry=is_retry,
        )
