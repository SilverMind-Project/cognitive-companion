"""Step plugin base classes and data transfer objects.

Every pipeline step handler inherits from :class:`StepHandler` and declares
its metadata via the :meth:`StepHandler.metadata` classmethod.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.core.registry import HasMetadata
from backend.models.pipeline import PipelineStep, WorkflowExecution

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
    next_step_id: int | None = None
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


@dataclass
class ServiceContainer:
    """Bag of services injected into step handlers at execution time.

    Steps request only what they need from here; they never import
    concrete service classes directly.
    """

    db_factory: Callable
    person_tracking: Any = None  # Used by person_identification; for activity ops use services.activity
    person_id_client: Any = None
    notification_dispatcher: Any = None
    ha_client: Any = None
    event_aggregator: Any = None
    scheduler: Any = None
    llm_model_registry: Any = None  # LLMModelRegistry for the unified llm_call step
    ha_state_cache: Any = None  # HaStateCache (Block 2)
    presence: Any = None  # PresenceService (Block 1)
    scene_analysis_client: Any = None
    daily_report_service: Any = None
    semantic_memory_client: Any = None
    interactive_response_service: Any = None
    memory_query: Any = None  # MemoryQueryService (Block 4)
    scene_intel: Any = None  # SceneIntelService (Block 4)
    activity: Any = None  # ActivityService (Block 5)
    signals: Any = None  # SignalsService (Block 10)
    knowledge_delivery: Any = None  # KnowledgeDeliveryService (knowledge feature)


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
