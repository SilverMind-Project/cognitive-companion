"""Typed FastAPI dependencies for :attr:`app.state` services.

Replaces the ``getattr(request.app.state, "name", None)`` anti-pattern
with strongly-typed, reusable ``Depends`` callables.  Each dependency
accesses ``request.app.state.<name>`` directly and raises **503** when
the service is not configured.

Usage::

    from backend.routers.dependencies import get_orchestrator_client

    @router.get("/foo")
    async def foo(
        client: OrchestratorClient = Depends(get_orchestrator_client),
    ) -> dict:
        ...

Notes
-----
- Every service MUST be initialised on ``app.state`` in
  :func:`backend.main.create_app` (set to ``None`` when unavailable)
  so that direct attribute access never raises ``AttributeError``.
- Dependencies are named ``get_<attr_name>`` to match the
  ``app.state`` attribute name, not the class name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status

from backend.core.database import get_session

if TYPE_CHECKING:
    from backend.integrations.homeassistant import HomeAssistantClient
    from backend.integrations.ingress_admin_client import IngressAdminClient
    from backend.integrations.llm import LLMModelRegistry, RealtimeLLMProvider
    from backend.integrations.minio_client import MinioClient
    from backend.integrations.tracking_orchestrator_client import OrchestratorClient
    from backend.mcp.gemini_adapter import GeminiToolAdapter
    from backend.services.companion_surface import CompanionSurfaceService
    from backend.services.conversation_manager import ConversationManager
    from backend.services.cts.identity_correction_service import IdentityCorrectionService
    from backend.services.cts.keyframe_read_service import KeyframeReadService
    from backend.services.cts.ph_enrichment import PHEnrichmentService
    from backend.services.cts.reid_review_service import ReIDReviewService
    from backend.services.cts.runtime import CTSRuntime
    from backend.services.daily_living_health import DailyLivingHealthService
    from backend.services.event_aggregator import EventAggregator
    from backend.services.guided_task.metrics_service import GuidedMetricsService
    from backend.services.guided_task.service import GuidedTaskService
    from backend.services.inference_telemetry import InferenceTelemetryService
    from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
    from backend.services.media_observability import MediaObservabilityService
    from backend.services.occupancy import OccupancyReadModel
    from backend.services.person_location.service import PersonLocationService
    from backend.services.scheduler import SchedulerBridge
    from backend.services.sensor_polling import SensorPollingService
    from backend.services.signals.feed import SignalsFeedService
    from backend.services.visitors import VisitorAdminService
    from backend.services.zones import ZoneService
    from backend.websocket.connection_manager import ConnectionManager

__all__ = [
    "get_companion_surface_service",
    "get_config_minio_client",
    "get_conversation_manager",
    "get_cts_runtime",
    "get_daily_living_health",
    "get_event_aggregator",
    "get_gemini_adapter",
    "get_guided_metrics_service",
    "get_guided_task_service",
    "get_ha_client",
    "get_identity_correction_service",
    "get_inference_telemetry",
    "get_ingress_admin_client",
    "get_keyframe_read_service",
    "get_knowledge_delivery",
    "get_llm_model_registry",
    "get_media_observability",
    "get_minio_client",
    "get_occupancy_read_model",
    "get_orchestrator_client",
    "get_person_location_service",
    "get_ph_enrichment_service",
    "get_realtime_provider",
    "get_scheduler",
    "get_sensor_polling",
    "get_signals_feed",
    "get_visitor_admin_service",
    "get_ws_manager",
    "get_zone_service",
]


def _raise_503(attr: str, description: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "service.unavailable",
            "message": f"{description} is not configured.",
        },
    )


# -- CTS gateway clients ------------------------------------------------------


def get_orchestrator_client(request: Request) -> OrchestratorClient:
    """Return the lifespan-managed tracking orchestrator client (503 if unavailable)."""
    client: OrchestratorClient | None = request.app.state.orchestrator_client
    if client is None:
        raise _raise_503("orchestrator_client", "Tracking orchestrator client")
    return client


def get_ph_enrichment_service(request: Request) -> PHEnrichmentService:
    """Return the lifespan-managed PH enrichment service (503 if unavailable)."""
    service: PHEnrichmentService | None = request.app.state.ph_enrichment_service
    if service is None:
        raise _raise_503("ph_enrichment_service", "PH enrichment service")
    return service


def get_keyframe_read_service(request: Request) -> KeyframeReadService:
    """Return the lifespan-managed M07 keyframe read service (503 if unavailable)."""
    service: KeyframeReadService | None = request.app.state.keyframe_read_service
    if service is None:
        raise _raise_503("keyframe_read_service", "Keyframe read service")
    return service


def get_identity_correction_service(request: Request) -> IdentityCorrectionService:
    """Return the lifespan-managed M08 identity correction service (503 if unavailable)."""
    service: IdentityCorrectionService | None = request.app.state.identity_correction_service
    if service is None:
        raise _raise_503("identity_correction_service", "Identity correction service")
    return service


def get_reid_review_service(request: Request) -> ReIDReviewService:
    """Return the lifespan-managed M09 ReID review service (503 if unavailable)."""
    service: ReIDReviewService | None = request.app.state.reid_review_service
    if service is None:
        raise _raise_503("reid_review_service", "ReID review service")
    return service


def get_visitor_admin_service(request: Request) -> VisitorAdminService:
    """Return the lifespan-managed visitor admin service (503 if unavailable)."""
    service: VisitorAdminService | None = request.app.state.visitor_admin_service
    if service is None:
        raise _raise_503("visitor_admin_service", "Visitor admin service")
    return service


def get_ingress_admin_client(request: Request) -> IngressAdminClient:
    """Return the lifespan-managed RTSP ingress admin client (503 if unavailable)."""
    client: IngressAdminClient | None = request.app.state.ingress_admin_client
    if client is None:
        raise _raise_503("ingress_admin_client", "RTSP ingress admin client")
    return client


def get_cts_runtime(request: Request) -> CTSRuntime:
    """Return the lifespan-managed CTS runtime (503 if unavailable)."""
    runtime: CTSRuntime | None = request.app.state.cts_runtime
    if runtime is None:
        raise _raise_503("cts_runtime", "CTS runtime")
    return runtime


# -- Integration clients ------------------------------------------------------


def get_minio_client(request: Request) -> MinioClient:
    """Return the lifespan-managed MinIO client (503 if unavailable)."""
    client: MinioClient | None = request.app.state.minio_client
    if client is None:
        raise _raise_503("minio_client", "MinIO client")
    return client


def get_config_minio_client(request: Request) -> MinioClient:
    """Return the lifespan-managed config MinIO client for static assets (503 if unavailable)."""
    client: MinioClient | None = request.app.state.config_minio_client
    if client is None:
        raise _raise_503("config_minio_client", "Config MinIO client")
    return client


def get_ha_client(request: Request) -> HomeAssistantClient:
    """Return the lifespan-managed Home Assistant client (503 if unavailable)."""
    client: HomeAssistantClient | None = request.app.state.ha_client
    if client is None:
        raise _raise_503("ha_client", "Home Assistant client")
    return client


# -- Application services -----------------------------------------------------


def get_conversation_manager(request: Request) -> ConversationManager:
    """Return the lifespan-managed conversation manager (503 if unavailable)."""
    svc: ConversationManager | None = request.app.state.conversation_manager
    if svc is None:
        raise _raise_503("conversation_manager", "Conversation manager")
    return svc


def get_companion_surface_service(request: Request) -> CompanionSurfaceService:
    """Return the lifespan-managed companion surface service (503 if unavailable)."""
    svc: CompanionSurfaceService | None = request.app.state.companion_surface_service
    if svc is None:
        raise _raise_503("companion_surface_service", "Companion surface service")
    return svc


def get_event_aggregator(request: Request) -> EventAggregator:
    """Return the lifespan-managed event aggregator (503 if unavailable)."""
    svc: EventAggregator | None = request.app.state.event_aggregator
    if svc is None:
        raise _raise_503("event_aggregator", "Event aggregator")
    return svc


def get_media_observability(request: Request) -> MediaObservabilityService:
    """Return the lifespan-managed media observability service (503 if unavailable)."""
    svc: MediaObservabilityService | None = request.app.state.media_observability
    if svc is None:
        raise _raise_503("media_observability", "Media observability service")
    return svc


def get_daily_living_health(request: Request) -> DailyLivingHealthService:
    """Return the lifespan-managed Daily Living health service (503 if unavailable)."""
    svc: DailyLivingHealthService | None = request.app.state.daily_living_health
    if svc is None:
        raise _raise_503("daily_living_health", "Daily Living health service")
    return svc


def get_sensor_polling(request: Request) -> SensorPollingService:
    """Return the lifespan-managed sensor polling service (503 if unavailable)."""
    svc: SensorPollingService | None = request.app.state.sensor_polling
    if svc is None:
        raise _raise_503("sensor_polling", "Sensor polling service")
    return svc


def get_signals_feed(request: Request) -> SignalsFeedService:
    """Return the lifespan-managed unified signals feed (503 if unavailable)."""
    svc: SignalsFeedService | None = request.app.state.signals_feed
    if svc is None:
        raise _raise_503("signals_feed", "Signals feed service")
    return svc


def get_scheduler(request: Request) -> SchedulerBridge:
    """Return the lifespan-managed scheduler bridge (503 if unavailable)."""
    svc: SchedulerBridge | None = request.app.state.scheduler
    if svc is None:
        raise _raise_503("scheduler", "Scheduler bridge")
    return svc


def get_inference_telemetry(request: Request) -> InferenceTelemetryService:
    """Return the lifespan-managed LLM admission telemetry service (503 if unavailable)."""
    svc: InferenceTelemetryService | None = request.app.state.inference_telemetry
    if svc is None:
        raise _raise_503("inference_telemetry", "Inference telemetry service")
    return svc


def get_llm_model_registry(request: Request) -> LLMModelRegistry:
    """Return the lifespan-managed LLM model registry (503 if unavailable)."""
    svc: LLMModelRegistry | None = request.app.state.llm_model_registry
    if svc is None:
        raise _raise_503("llm_model_registry", "LLM model registry")
    return svc


def get_ws_manager(request: Request) -> ConnectionManager:
    """Return the lifespan-managed WebSocket connection manager (503 if unavailable)."""
    svc: ConnectionManager | None = request.app.state.ws_manager
    if svc is None:
        raise _raise_503("ws_manager", "WebSocket connection manager")
    return svc


def get_realtime_provider(request: Request) -> RealtimeLLMProvider | None:
    """Return the lifespan-managed realtime LLM provider, or None if not configured."""
    return request.app.state.realtime_provider  # type: ignore[no-any-return]


def get_gemini_adapter(request: Request) -> GeminiToolAdapter:
    """Return the lifespan-managed Gemini tool adapter (503 if unavailable)."""
    svc: GeminiToolAdapter | None = request.app.state.gemini_adapter
    if svc is None:
        raise _raise_503("gemini_adapter", "Gemini tool adapter")
    return svc


def get_knowledge_delivery(request: Request) -> KnowledgeDeliveryService:
    """Return the lifespan-managed knowledge delivery service (503 if unavailable)."""
    svc: KnowledgeDeliveryService | None = request.app.state.knowledge_delivery
    if svc is None:
        raise _raise_503("knowledge_delivery", "Knowledge delivery service")
    return svc


def get_guided_task_service(request: Request) -> GuidedTaskService:
    """Return the lifespan-managed guided-task service (503 if unavailable)."""
    svc: GuidedTaskService | None = request.app.state.guided_task_service
    if svc is None:
        raise _raise_503("guided_task_service", "Guided task service")
    return svc


def get_guided_metrics_service(request: Request) -> GuidedMetricsService:
    """Return the lifespan-managed guided-task metrics service (503 if unavailable)."""
    svc: GuidedMetricsService | None = request.app.state.guided_metrics_service
    if svc is None:
        raise _raise_503("guided_metrics_service", "Guided task metrics service")
    return svc


def get_zone_service(request: Request) -> ZoneService:
    """Return the lifespan-managed room-zone service (503 if unavailable)."""
    svc: ZoneService | None = request.app.state.zone_service
    if svc is None:
        raise _raise_503("zone_service", "Room zone service")
    return svc


def get_occupancy_read_model(request: Request) -> OccupancyReadModel:
    """Return the lifespan-managed occupancy read-model (503 if unavailable)."""
    svc: OccupancyReadModel | None = request.app.state.occupancy_read_model
    if svc is None:
        raise _raise_503("occupancy_read_model", "Occupancy read-model")
    return svc


def get_person_location_service(request: Request) -> PersonLocationService:
    """Return a per-request PersonLocationService (503 if unavailable)."""
    try:
        from backend.services.person_location.repositories import (
            SqlAlchemyObservationRepository,
            SqlAlchemySegmentRepository,
        )
        from backend.services.person_location.service import PersonLocationService

        return PersonLocationService(
            obs_repo=SqlAlchemyObservationRepository(get_session),
            seg_repo=SqlAlchemySegmentRepository(get_session),
        )
    except Exception as exc:
        raise _raise_503("person_location_service", "Person location service") from exc
