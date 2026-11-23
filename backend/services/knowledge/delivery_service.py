"""Pipeline-side delivery: ws fanout, eink render, Gemini Live voice, quiz lifecycle.

Info card delivery lives here; the quiz session lifecycle is
:class:`~backend.services.knowledge.quiz_delivery.QuizDeliveryMixin`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.integrations.eink_renderer import EInkRenderer
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import InfoCard, InfoCardDelivery
from backend.services.interactive_session import WorkflowResumeScheduler
from backend.services.knowledge.delivery_result import DeliveryResult
from backend.services.knowledge.quiz_delivery import QuizDeliveryMixin
from backend.services.knowledge.voice_instructions import VoiceInstructionConfig
from backend.websocket.connection_manager import ConnectionManager

logger = get_logger(__name__)

__all__ = ["DeliveryResult", "KnowledgeDeliveryService"]


class KnowledgeDeliveryService(QuizDeliveryMixin):
    """Delivers info cards and quizzes via ws popup, eink, and Gemini Live voice."""

    def __init__(
        self,
        db_factory,
        ws_manager: ConnectionManager,
        minio_client: MinioClient | None = None,
        eink_renderer: EInkRenderer | None = None,
        voice_instructions: VoiceInstructionConfig | None = None,
        content_generation: Any = None,
        *,
        scheduler: WorkflowResumeScheduler | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._ws_manager = ws_manager
        self._minio = minio_client
        self._eink = eink_renderer
        self._voice = voice_instructions
        self._content_gen = content_generation
        self._scheduler = scheduler

    def attach_scheduler(self, scheduler: WorkflowResumeScheduler) -> None:
        """Bind the scheduler once it exists (it is built after the knowledge phase).

        The early pipeline resume when a quiz completes goes through it.
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
    ) -> DeliveryResult:
        """Broadcast info_card ws message, render eink, send voice prompt."""
        db: Session = self._db_factory()
        try:
            # Audit row
            delivery = InfoCardDelivery(
                info_card_id=card.id,
                rule_id=rule_id,
                execution_id=execution_id,
                channels=channels,
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)
            delivery_id = delivery.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # Resolve voice instruction
        if self._voice:
            voice_inst = self._voice.compose(
                step_type="info_card",
                base_instruction="",
                step_override=voice_instruction or None,
                resource_override=card.voice_instruction or None,
            )
        else:
            voice_inst = voice_instruction or card.voice_instruction or ""

        # Build image slots for PWA
        image_slots: list[dict[str, Any]] = []
        if "pwa" in channels:
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

        # PWA popup broadcast
        if "pwa" in channels:
            try:
                await self._ws_manager.broadcast(
                    {
                        "type": "info_card",
                        "delivery_id": delivery_id,
                        "layout_id": card.layout_id,
                        "title": card.title,
                        "body": card.body_text,
                        "image_slots": image_slots,
                        "dismiss_seconds": dismiss_seconds,
                        "server_timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception:
                logger.exception("info_card_ws_broadcast_failed")

        # Eink rendering
        if "eink" in channels and self._eink:
            try:
                # Resolve eink image variant from the first image slot
                eink_image_bytes: bytes | None = None
                for slot in card.image_slots or []:
                    variants = slot.variants if isinstance(slot.variants, dict) else {}
                    eink_var = variants.get("eink", {})
                    object_name = eink_var.get("object_name") or slot.original_object_name
                    if object_name and self._minio:
                        try:
                            eink_image_bytes = await self._minio.async_get_object(object_name)
                        except Exception:
                            logger.exception("eink_image_fetch_failed", object_name=object_name)
                    break  # Use only the first image slot for eink

                await self._eink.render(
                    text=f"{card.title}\n\n{card.body_text}",
                    template="info_card",
                    expires_in_minutes=eink_expiry_minutes,
                    overlay_image=eink_image_bytes,
                )
            except Exception:
                logger.exception("info_card_eink_render_failed")

        # Voice delivery via Gemini Live (gated on explicit speak flag)
        if speak:
            try:
                voice_prompt = (
                    f"Here is some information for you.\n\n{card.title}\n\n{card.body_text}"
                )
                await self._ws_manager.send_backend_task(
                    prompt=voice_prompt,
                    voice_instruction=voice_inst or None,
                    metadata={
                        "delivery_type": "info_card",
                        "delivery_id": delivery_id,
                        "execution_id": execution_id,
                        "info_card_id": card.id,
                    },
                )
            except Exception:
                logger.exception("info_card_voice_delivery_failed")

        logger.info(
            "info_card_delivered",
            delivery_id=delivery_id,
            card_id=card.id,
            channels=channels,
        )
        return DeliveryResult(delivery_id=delivery_id)

    # -- info card events ---------------------------------------------------

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
            elif action in ("dismissed", "timeout"):
                delivery.dismissed_at = now
                delivery.dismissed_by = "senior"
            db.commit()
            return delivery
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
