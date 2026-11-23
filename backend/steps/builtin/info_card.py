"""Info card pipeline step. Delivers a curated info card via PWA, eink, and voice."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.core.logging import get_logger
from backend.models.knowledge import InfoCard
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps._helpers import make_trigger_vars, resolve_person_id
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
                        "items": {"enum": ["pwa", "eink", "voice"]},
                        "minItems": 1,
                    },
                    "pwa_dismiss_seconds": {"type": "integer", "default": 60},
                    "eink_expiry_minutes": {"type": "integer", "default": 30},
                    "trigger_cooloff": {"type": "boolean", "default": True},
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Resident the card is for (fills {{senior_name}}); defaults "
                            "to the person in the trigger or upstream steps."
                        ),
                    },
                    "voice_instruction": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Added to the companion's persona while this card is read "
                            "aloud. Supports {{template}} syntax (e.g. {{senior_name}})."
                        ),
                    },
                },
                "required": ["info_card_id", "channels"],
            },
            default_config={
                "channels": ["pwa"],
                "pwa_dismiss_seconds": 60,
                "eink_expiry_minutes": 30,
                "trigger_cooloff": True,
                "person_id": "",
                "voice_instruction": "",
            },
            output_schema={
                "type": "object",
                "properties": {
                    "info_card_id": {"type": "integer"},
                    "delivery_id": {"type": "integer"},
                    "channels": {"type": "array", "items": {"type": "string"}},
                },
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
            # Image slots are eager-loaded: delivery reads them after this session
            # closes, and a lazy load on the detached card would raise.
            card = db.execute(
                select(InfoCard)
                .options(selectinload(InfoCard.image_slots))
                .where(InfoCard.id == card_id)
            ).scalar_one_or_none()
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
        delivery_svc = services.knowledge_delivery
        if delivery_svc is None:
            return StepResult(
                success=False, data={"error": "knowledge delivery service not available"}
            )

        result = await delivery_svc.deliver_info_card(
            card=card,
            channels=channels,
            execution_id=execution.id,
            rule_id=step.rule_id,
            voice_instruction=voice_instruction or None,
            speak=("voice" in channels),
            dismiss_seconds=dismiss_seconds,
            eink_expiry_minutes=eink_expiry,
            senior_id=resolve_person_id(config, pipeline_data),
            template_data=pipeline_data,
            trigger_vars=make_trigger_vars(trigger),
        )

        logger.info(
            "info_card_step_executed",
            card_id=card_id,
            delivery_id=result.delivery_id,
            channels=channels,
        )
        result_data: dict = {
            "info_card_id": card_id,
            "delivery_id": result.delivery_id,
            "channels": channels,
        }
        if config.get("trigger_cooloff", True):
            result_data["_cooloff_triggered"] = True
        return StepResult(data=result_data)
