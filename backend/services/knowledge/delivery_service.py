"""Pipeline-side delivery: ws fanout, eink render, Gemini Live voice, quiz lifecycle.

Info card delivery lives here; the quiz session lifecycle is
:class:`~backend.services.knowledge.quiz_delivery.QuizDeliveryMixin` and the shared
template and voice-instruction handling is
:class:`~backend.services.knowledge.delivery_context.DeliveryContextMixin`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.eink_renderer import EInkRenderer
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import InfoCard, InfoCardDelivery
from backend.services.interactive_session import WorkflowResumeScheduler, voice_owner_key
from backend.services.knowledge.delivery_result import DeliveryResult
from backend.services.knowledge.quiz_delivery import QuizDeliveryMixin
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

if TYPE_CHECKING:
    from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)

__all__ = ["DeliveryResult", "KnowledgeDeliveryService"]

INFO_CARD_DELIVERY_TYPE = "info_card"
_CLOSING_CARD_ACTIONS = frozenset({"dismissed", "timeout"})


class KnowledgeDeliveryService(QuizDeliveryMixin):
    """Delivers info cards and quizzes via ws popup, eink, and Gemini Live voice."""

    def __init__(
        self,
        db_factory: Callable[[], Session],
        ws_manager: ConnectionManager,
        minio_client: MinioClient | None = None,
        eink_renderer: EInkRenderer | None = None,
        voice_instructions: VoiceInstructionConfig | None = None,
        content_generation: Any = None,
        *,
        base_instruction: str = "",
        scheduler: WorkflowResumeScheduler | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._ws_manager = ws_manager
        self._minio = minio_client
        self._eink = eink_renderer
        self._voice = voice_instructions
        self._content_gen = content_generation
        self._base_instruction = base_instruction
        self._scheduler = scheduler
        self._voice_sessions: set[int] = set()
        # Bounded: an entry is dropped when its delivery ends, and the TTL only caps
        # memory for a card nobody ever closed (its device lease has long expired).
        self._delivery_surfaces: TTLCache[str, str] = TTLCache(maxsize=1024, ttl=24 * 3600)

    def attach_scheduler(self, scheduler: WorkflowResumeScheduler) -> None:
        """Bind the scheduler once it exists (it is built after the knowledge phase).

        Quiz timeouts and pipeline resumes go through it.
        """
        self._scheduler = scheduler

    # -- info card delivery -------------------------------------------------

    async def deliver_info_card(
        self,
        card: InfoCard,
        *,
        channels: list[str],
        execution_id: int,
        rule_id: int | None = None,
        voice_instruction: str | None = None,
        speak: bool = False,
        dismiss_seconds: int = 60,
        eink_expiry_minutes: int = 30,
        senior_id: str | None = None,
        template_data: Mapping[str, Any] | None = None,
        trigger_vars: Mapping[str, Any] | None = None,
        surface_id: str | None = None,
    ) -> DeliveryResult:
        """Show the card on the tablet and e-ink and read it aloud, as ``channels`` ask.

        ``{{ }}`` templates in the card's title, body, and voice instruction (and the
        step's ``voice_instruction``) render against the pipeline data, trigger, and
        ``senior_name``. ``surface_id`` is the companion surface in her room: the card
        and its voice go there (every screen when None), and that surface is woken.
        """
        db: Session = self._db_factory()
        try:
            delivery = InfoCardDelivery(
                info_card_id=card.id,
                rule_id=rule_id,
                execution_id=execution_id,
                channels=channels,
            )
            db.add(delivery)
            db.commit()
            delivery_id = delivery.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        context = self._template_context(template_data, trigger_vars, senior_id)
        title = self._render(card.title, context)
        body = self._render(card.body_text, context)
        owner = voice_owner_key(INFO_CARD_DELIVERY_TYPE, delivery_id)
        if "pwa" in channels or speak:
            await self._engage_resident_surface(
                owner,
                surface_id,
                reason=INFO_CARD_DELIVERY_TYPE,
                turn_seconds=dismiss_seconds,
                microphone=speak,
            )

        if "pwa" in channels:
            await self._broadcast_info_card(card, delivery_id, title, body, dismiss_seconds)
        if "eink" in channels and self._eink:
            await self._render_info_card_eink(self._eink, card, title, body, eink_expiry_minutes)

        if speak:
            composed = self._compose_voice(
                "info_card",
                step_override=voice_instruction,
                resource_override=card.voice_instruction,
                context=context,
            )
            try:
                await self._ws_manager.send_backend_task(
                    # An instruction to the agent, not words from the senior: sent bare,
                    # the agent acknowledged the card ("Noted") instead of reading it.
                    prompt=(
                        "Read this information card aloud to the senior, warmly and "
                        f'slowly, then ask if they have any questions. Title: "{title}". '
                        f'Card: "{body}"'
                    ),
                    voice_instruction=composed or None,
                    metadata={
                        "delivery_type": INFO_CARD_DELIVERY_TYPE,
                        "delivery_id": delivery_id,
                        "execution_id": execution_id,
                        "info_card_id": card.id,
                    },
                    surface_id=self._resident_surface(owner),
                )
            except Exception:
                logger.exception("info_card_voice_delivery_failed", delivery_id=delivery_id)

        logger.info(
            "info_card_delivered",
            delivery_id=delivery_id,
            card_id=card.id,
            channels=channels,
        )
        return DeliveryResult(delivery_id=delivery_id)

    async def _broadcast_info_card(
        self,
        card: InfoCard,
        delivery_id: int,
        title: str,
        body: str,
        dismiss_seconds: int,
    ) -> None:
        image_slots: list[dict[str, Any]] = []
        for slot in card.image_slots or []:
            pwa_var = slot.variants.get("pwa", {}) if isinstance(slot.variants, dict) else {}
            object_name = pwa_var.get("object_name", slot.original_object_name)
            url = ""
            if object_name and self._minio:
                try:
                    url = self._minio.generate_presigned_url(object_name)
                except Exception:
                    logger.exception("presigned_url_failed", object_name=object_name)
            image_slots.append(
                {
                    "slot_id": slot.slot_index,
                    "alt_text": slot.alt_text or "",
                    "url": url,
                    "width": pwa_var.get("width", 0),
                    "height": pwa_var.get("height", 0),
                }
            )
        try:
            await self._send_to_resident(
                voice_owner_key(INFO_CARD_DELIVERY_TYPE, delivery_id),
                {
                    "type": "info_card",
                    "delivery_id": delivery_id,
                    "layout_id": card.layout_id,
                    "title": title,
                    "body": body,
                    "image_slots": image_slots,
                    "dismiss_seconds": dismiss_seconds,
                    "server_timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            logger.exception("info_card_ws_broadcast_failed")

    async def _render_info_card_eink(
        self,
        eink: EInkRenderer,
        card: InfoCard,
        title: str,
        body: str,
        eink_expiry_minutes: int,
    ) -> None:
        try:
            eink_image_bytes: bytes | None = None
            # E-ink shows only the first slot's image.
            for slot in (card.image_slots or [])[:1]:
                variants = slot.variants if isinstance(slot.variants, dict) else {}
                eink_var = variants.get("eink", {})
                object_name = eink_var.get("object_name") or slot.original_object_name
                if object_name and self._minio:
                    try:
                        eink_image_bytes = await self._minio.async_get_object(object_name)
                    except Exception:
                        logger.exception("eink_image_fetch_failed", object_name=object_name)

            await eink.render(
                text=f"{title}\n\n{body}",
                template="info_card",
                expires_in_minutes=eink_expiry_minutes,
                overlay_image=eink_image_bytes,
            )
        except Exception:
            logger.exception("info_card_eink_render_failed")

    # -- info card events ---------------------------------------------------

    async def handle_info_card_event(
        self, delivery_id: int, action: str
    ) -> InfoCardDelivery | None:
        """Record a tablet event on a delivered card; closing it drops the card persona."""
        delivery = self.record_info_card_event(delivery_id, action)
        if action in _CLOSING_CARD_ACTIONS:
            await self._release_resident(
                voice_owner_key(INFO_CARD_DELIVERY_TYPE, delivery_id),
                reason=INFO_CARD_DELIVERY_TYPE,
            )
        return delivery

    def record_info_card_event(self, delivery_id: int, action: str) -> InfoCardDelivery | None:
        """Update viewed_at or dismissed_at on the delivery audit row."""
        db: Session = self._db_factory()
        try:
            delivery = db.execute(
                select(InfoCardDelivery).where(InfoCardDelivery.id == delivery_id)
            ).scalar_one_or_none()
            if delivery is None:
                return None
            now = datetime.now(UTC)
            if action == "viewed":
                delivery.viewed_at = now
            elif action in _CLOSING_CARD_ACTIONS:
                delivery.dismissed_at = now
                delivery.dismissed_by = "senior"
            db.commit()
            return delivery
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
