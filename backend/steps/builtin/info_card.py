"""Info card pipeline step. Delivers a curated info card via PWA, eink, and voice."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.logging import get_logger
from backend.models.knowledge import InfoCard
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


@StepRegistry.register
class InfoCardStep(StepHandler):
    """Pipeline step for delivering an info card to the senior."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="info_card",
            display_name="Info Card",
            category="action",
            icon="mdi-card-text-outline",
            description="Show a curated info card on PWA, eink, or both.",
            config_schema={
                "type": "object",
                "properties": {
                    "info_card_id": {"type": "integer"},
                    "channels": {
                        "type": "array",
                        "items": {"enum": ["pwa", "eink"]},
                        "minItems": 1,
                    },
                    "pwa_dismiss_seconds": {"type": "integer", "default": 60},
                    "eink_expiry_minutes": {"type": "integer", "default": 30},
                    "trigger_cooloff": {"type": "boolean", "default": True},
                    "voice_instruction": {
                        "type": "string",
                        "default": "",
                        "description": "Override the Gemini Live system instruction for this delivery.",
                    },
                },
                "required": ["info_card_id", "channels"],
            },
            default_config={
                "channels": ["pwa"],
                "pwa_dismiss_seconds": 60,
                "eink_expiry_minutes": 30,
                "trigger_cooloff": True,
                "voice_instruction": "",
            },
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}
        card_id = config.get("info_card_id")
        if not card_id:
            return StepResult(success=False, data={"error": "info_card_id is required"})

        channels = config.get("channels", ["pwa"])
        dismiss_seconds = config.get("pwa_dismiss_seconds", 60)
        eink_expiry = config.get("eink_expiry_minutes", 30)
        voice_instruction = config.get("voice_instruction", "")

        # Load the info card
        db: Session = services.db_factory()
        try:
            card = db.execute(select(InfoCard).where(InfoCard.id == card_id)).scalar_one_or_none()
            if card is None:
                return StepResult(success=False, data={"error": f"Info card {card_id} not found"})
            if card.status != "approved":
                return StepResult(
                    success=False,
                    data={"error": f"Info card {card_id} is not approved (status: {card.status})"},
                )
        finally:
            db.close()

        # Delivery
        delivery_svc = None
        if hasattr(services, "_delivery_service"):
            delivery_svc = services._delivery_service

        if delivery_svc is None:
            from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
            # We need ws_manager from the notification dispatcher
            ws_manager = None
            if services.notification_dispatcher and hasattr(
                services.notification_dispatcher, "_dispatch_services"
            ):
                ws_manager = services.notification_dispatcher._dispatch_services.ws_manager
            if ws_manager is None:
                return StepResult(
                    success=False, data={"error": "WebSocket manager not available"}
                )
            delivery_svc = KnowledgeDeliveryService(
                db_factory=services.db_factory,
                ws_manager=ws_manager,
            )

        result = await delivery_svc.deliver_info_card(
            card=card,
            channels=channels,
            execution_id=execution.id,
            rule_id=step.rule_id,
            voice_instruction=voice_instruction or None,
            dismiss_seconds=dismiss_seconds,
            eink_expiry_minutes=eink_expiry,
        )

        logger.info(
            "info_card_step_executed",
            card_id=card_id,
            delivery_id=result.delivery_id,
            channels=channels,
        )
        return StepResult(
            data={
                "info_card_id": card_id,
                "delivery_id": result.delivery_id,
                "channels": channels,
            }
        )
