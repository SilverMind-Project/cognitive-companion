"""Shared per-delivery context: template data and the composed realtime instruction.

Part of :class:`~backend.services.knowledge.delivery_service.KnowledgeDeliveryService`.
Every senior-facing delivery renders caregiver-authored ``{{ }}`` templates against
the same context and composes its realtime instruction on top of the companion's
base persona, never in place of it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from backend.core.template import render_template
from backend.models.person import HouseholdMember
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

if TYPE_CHECKING:
    from backend.websocket.connection_manager import ConnectionManager


class DeliveryContextMixin:
    """Template context, instruction composition, and persona release for deliveries."""

    _db_factory: Callable[[], Session]
    _ws_manager: ConnectionManager
    _voice: VoiceInstructionConfig | None
    _base_instruction: str

    def _template_context(
        self,
        template_data: Mapping[str, Any] | None,
        trigger_vars: Mapping[str, Any] | None,
        senior_id: str | None,
    ) -> dict[str, Any]:
        """Pipeline data plus ``trigger.*`` and ``senior_name``.

        ``senior_name`` resolves to an empty string when no resident is known, so a
        template never reaches the senior as a literal ``{{senior_name}}``.
        """
        context: dict[str, Any] = dict(template_data or {})
        if trigger_vars:
            context["trigger"] = dict(trigger_vars)
            for key, value in trigger_vars.items():
                context.setdefault(key, value)
        context.setdefault("senior_name", self._senior_name(senior_id))
        return context

    def _senior_name(self, senior_id: str | None) -> str:
        if not senior_id:
            return ""
        db: Session = self._db_factory()
        try:
            member = db.get(HouseholdMember, senior_id)
            return member.name if member is not None and member.name else ""
        finally:
            db.close()

    @staticmethod
    def _render(text: str, context: Mapping[str, Any]) -> str:
        return render_template(text, context) if text else text

    def _compose_voice(
        self,
        step_type: str,
        *,
        step_override: str | None,
        resource_override: str | None,
        context: Mapping[str, Any],
        directive: str = "",
    ) -> str:
        """Base persona + this delivery's instruction (+ an optional mode directive)."""
        if self._voice is None:
            per_delivery = self._render(step_override or resource_override or "", context)
            parts = [p for p in (self._base_instruction, per_delivery, directive) if p]
            return "\n\n".join(parts)
        return self._voice.compose(
            step_type,
            base_instruction=self._base_instruction,
            step_override=step_override or None,
            resource_override=resource_override or None,
            context=context,
            directive=directive,
        )

    def compose_voice_instruction(
        self,
        step_type: str,
        *,
        step_override: str | None,
        template_data: Mapping[str, Any] | None = None,
        trigger_vars: Mapping[str, Any] | None = None,
        senior_id: str | None = None,
    ) -> str | None:
        """The realtime instruction for a pipeline step that speaks to the senior.

        Returns None when the step adds nothing to the base persona, so the live
        session is left as it is instead of being reopened with the same persona.
        """
        default = self._voice.default_for(step_type) if self._voice else ""
        if not step_override and not default:
            return None
        context = self._template_context(template_data, trigger_vars, senior_id)
        return (
            self._compose_voice(
                step_type, step_override=step_override, resource_override=None, context=context
            )
            or None
        )

    async def _release_voice(self, owner: str) -> None:
        """Restore the base persona if this delivery's instruction is still active."""
        await self._ws_manager.release_voice_instruction(owner)
