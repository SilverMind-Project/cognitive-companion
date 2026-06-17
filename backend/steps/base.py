"""Step plugin base classes and data transfer objects.

Every pipeline step handler inherits from :class:`StepHandler` and declares
its metadata via the :meth:`StepHandler.metadata` classmethod.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from backend.core.registry import HasMetadata
from backend.models.pipeline import PipelineStep, WorkflowExecution

if TYPE_CHECKING:
    from backend.integrations.ha_state_cache import HaStateCache
    from backend.integrations.homeassistant import HomeAssistantClient
    from backend.integrations.llm import LLMModelRegistry
    from backend.integrations.minio_client import MinioClient
    from backend.integrations.person_id_client import PersonIDClient
    from backend.integrations.scene_analysis_client import SceneAnalysisClient
    from backend.integrations.semantic_memory_client import SemanticMemoryClient
    from backend.services.activity.service import ActivityService
    from backend.services.cts.event_bucketizer import CtsEventBucketizer
    from backend.services.daily_report import DailyReportService
    from backend.services.event_aggregator import EventAggregator
    from backend.services.guided_task.service import GuidedTaskService
    from backend.services.interactive_response import InteractiveResponseService
    from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
    from backend.services.memory_query.service import MemoryQueryService
    from backend.services.notification_dispatcher import NotificationDispatcher
    from backend.services.person_tracking import PersonTrackingService
    from backend.services.presence.service import PresenceService
    from backend.services.scene_intel.service import SceneIntelService
    from backend.services.scheduler import SchedulerBridge
    from backend.services.signals.service import SignalsService

# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class TriggerContext:
    """Metadata about what triggered a pipeline execution."""

    trigger_type: str  # sensor_event, cron, manual, webhook, resume, occupancy_duration
    sensor_id: str | None = None
    room_name: str | None = None
    media_paths: list[str] = field(default_factory=list)
    media_type: str = "image"
    webhook_payload: dict | None = None
    occupancy_duration_minutes: float | None = None  # set for occupancy_duration triggers


@dataclass
class StepResult:
    """Output of a single pipeline step."""

    success: bool = True
    data: dict = field(default_factory=dict)
    should_continue: bool = True
    output_ports: tuple[str, ...] = ("main",)
    wait_until: datetime | None = None


@dataclass
class StepMetadata:
    """Declarative metadata for a step type, used by the registry and
    served to the frontend for auto-form generation."""

    type_name: str  # "person_identification"
    display_name: str  # "Person Identification"
    category: str  # perception | reasoning | action | state | flow
    icon: str  # "mdi-face-recognition"
    description: str
    config_schema: dict  # JSONSchema for config_json validation
    default_config: dict  # Default config_json for new steps
    deprecated: bool = False  # Whether this step type is deprecated

    # Plugin evolution
    schema_version: int = 1
    ui_hints_version: int = 1
    ui_hints: dict = field(default_factory=dict)  # x-ui widget hints for SchemaForm
    output_schema: dict = field(default_factory=dict)  # JSONSchema for step outputs
    tags: tuple[str, ...] = ()  # for palette grouping/search
    output_ports: tuple[str, ...] = ("main",)


@dataclass
class ServiceContainer:
    """Bag of services injected into step handlers at execution time.

    Steps request only what they need from here; they never import
    concrete service classes directly.
    """

    db_factory: Callable
    person_tracking: PersonTrackingService | None = None
    person_id_client: PersonIDClient | None = None
    notification_dispatcher: NotificationDispatcher | None = None
    ha_client: HomeAssistantClient | None = None
    event_aggregator: EventAggregator | None = None
    scheduler: SchedulerBridge | None = None
    rag_service: MemoryQueryService | None = None
    llm_model_registry: LLMModelRegistry | None = None
    ha_state_cache: HaStateCache | None = None
    presence: PresenceService | None = None
    scene_analysis_client: SceneAnalysisClient | None = None
    daily_report_service: DailyReportService | None = None
    semantic_memory_client: SemanticMemoryClient | None = None
    interactive_response_service: InteractiveResponseService | None = None
    memory_query: MemoryQueryService | None = None
    scene_intel: SceneIntelService | None = None
    activity: ActivityService | None = None
    signals: SignalsService | None = None
    knowledge_delivery: KnowledgeDeliveryService | None = None
    minio_client: MinioClient | None = None
    guided_task: GuidedTaskService | None = None
    # CTS sliding-window frame buffer, injected after CTS bootstrap. Read by the
    # canonical media poll step and its CTS alias.
    bucketizer: CtsEventBucketizer | None = None


# ---------------------------------------------------------------------------
# Step handler ABC
# ---------------------------------------------------------------------------


class StepHandler(HasMetadata[StepMetadata]):
    """Base class for all pipeline step handlers.

    Subclasses must implement :meth:`metadata` (class-level) and
    :meth:`execute` (instance-level).  Each handler is instantiated once
    at registry time and reused across executions.
    """

    @classmethod
    @abstractmethod
    def metadata(cls) -> StepMetadata:
        """Return step type metadata including config schema."""
        ...

    @abstractmethod
    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        """Execute the step. Return StepResult."""
        ...
