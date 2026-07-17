"""Bootstrap phase: perception clients and person/activity/signal services.

Moved verbatim from ``backend/main.py``'s lifespan (M20): person-ID, scene-
analysis and semantic-memory clients; memory query and scene-intel
services; the shared source authority; person tracking; the event
aggregator; activity session/domain services; daily report; interactive
response; signals; companion-surface/zone registries; the unified signals
feed; and the occupancy read-model.

Sits between the ``ServiceContainer``+``RulesEngine`` construction and the
pipeline executor in the original source (both of which need the fields
this phase assigns onto the shared container), so ``lifespan.py`` calls it
between the two halves of ``bootstrap.pipeline`` -- see ``bootstrap/README.md``.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.steps.base import ServiceContainer

logger = get_logger(__name__)


async def wire_perception(app: FastAPI, settings: Settings, container: ServiceContainer) -> None:
    minio_client = app.state.minio_client
    ha_client = app.state.ha_client
    ws_manager = app.state.ws_manager

    # -- Person identification client --------------------------------------
    from backend.integrations.person_id_client import PersonIDClient

    person_id_client = PersonIDClient()
    app.state.person_id_client = person_id_client

    # -- Scene analysis client --------------------------------------------
    from backend.integrations.scene_analysis_client import SceneAnalysisClient

    scene_analysis_client = SceneAnalysisClient()
    app.state.scene_analysis_client = scene_analysis_client
    container.scene_analysis_client = scene_analysis_client

    # -- Semantic memory client --------------------------------------------
    from backend.integrations.semantic_memory_client import SemanticMemoryClient

    _smc = SemanticMemoryClient()
    semantic_memory_client: SemanticMemoryClient | None = _smc if _smc.configured else None
    app.state.semantic_memory_client = semantic_memory_client
    container.semantic_memory_client = semantic_memory_client

    # Startup health check: warn if semantic_memory is enabled but unreachable.
    if semantic_memory_client is not None:
        try:
            healthy = await semantic_memory_client.health_check()
            if healthy is None:
                logger.warning(
                    "semantic_memory_startup_unreachable",
                    hint="Semantic Memory is configured in settings but unreachable. "
                    "Memory queries, scene_contains filters, and semantic_memory_write "
                    "steps will return empty results.",
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "semantic_memory_startup_unreachable",
                hint="Semantic Memory health check failed. "
                "Memory-dependent features will degrade gracefully.",
            )

    # -- Memory query service (Block 4) ------------------------------------
    from backend.services.memory_query import MemoryQueryService

    memory_cache_config = settings.section("memory_query.cache")
    mq_cache_enabled = memory_cache_config.as_bool("enabled")
    mq_cache_ttl = memory_cache_config.as_int("ttl_seconds")
    mq_cache_maxsize = memory_cache_config.as_int("maxsize")
    memory_query_service = MemoryQueryService(
        client=semantic_memory_client,
        cache_enabled=mq_cache_enabled,
        cache_ttl_seconds=mq_cache_ttl,
        cache_maxsize=mq_cache_maxsize,
    )
    app.state.memory_query = memory_query_service
    container.memory_query = memory_query_service

    # -- Scene intel service (Block 4) -------------------------------------
    from backend.services.scene_intel import SceneIntelService

    scene_intel_service = SceneIntelService(
        scene_client=scene_analysis_client,
        memory_client=semantic_memory_client,
    )
    app.state.scene_intel = scene_intel_service
    container.scene_intel = scene_intel_service

    # -- Source authority (sole arbiter for person location writes, CR-15) ---
    from backend.services.cts.source_authority import SourceAuthority

    shared_authority = SourceAuthority(
        cts_lock_s=settings.as_float("cts.lock_seconds"),
    )
    app.state.source_authority = shared_authority

    # -- Person tracking service -------------------------------------------
    from backend.services.person_tracking import PersonTrackingService

    person_tracking = PersonTrackingService(
        db_session_factory=get_session,
        person_id_client=person_id_client,
        ha_client=ha_client,
        ws_manager=ws_manager,
        authority=shared_authority,
    )
    app.state.person_tracking = person_tracking
    container.person_tracking = person_tracking

    # -- Event aggregator --------------------------------------------------
    from backend.services.event_aggregator import EventAggregator

    # Placeholder callback  will be replaced once workflow is wired
    async def _noop_callback(sensor_id: str, media_paths: list[str]):
        pass

    aggregator_config = settings.as_dict("event_aggregator")
    event_aggregator = EventAggregator(
        config=aggregator_config,
        db_session_factory=get_session,
        minio_client=minio_client,
        process_callback=_noop_callback,
    )
    app.state.event_aggregator = event_aggregator
    container.event_aggregator = event_aggregator

    # -- Activity session service ------------------------------------------
    from backend.services.activity_session import ActivitySessionService

    activity_session_service = ActivitySessionService(get_session)
    app.state.activity_session_service = activity_session_service

    # -- Activity domain service (Block 5) ---------------------------------
    from backend.services.activity import ActivityService

    activity_service = ActivityService(
        person_tracking=person_tracking,
        activity_session=activity_session_service,
    )
    app.state.activity_service = activity_service
    container.activity = activity_service

    # -- Daily report service ----------------------------------------------
    from backend.services.daily_report import DailyReportService

    daily_report_service = DailyReportService(get_session)
    app.state.daily_report_service = daily_report_service
    container.daily_report_service = daily_report_service

    # -- Interactive response service --------------------------------------
    from backend.services.interactive_response import InteractiveResponseService

    # Note: scheduler will be injected after it's created below
    interactive_response_service = InteractiveResponseService(
        db_factory=get_session,
        scheduler=None,  # Injected later
    )
    app.state.interactive_response_service = interactive_response_service
    container.interactive_response_service = interactive_response_service

    # -- SignalsService (Block 10) -----------------------------------------
    from backend.services.signals import SignalsService

    signals_service = SignalsService(db_factory=get_session)
    app.state.signals = signals_service
    container.signals = signals_service

    # -- Companion surface registry ----------------------------------------
    from backend.services.companion_surface import CompanionSurfaceService
    from backend.services.zones import ZoneService

    companion_surface_service = CompanionSurfaceService(
        db_factory=get_session,
        person_location_service=None,
    )
    app.state.companion_surface_service = companion_surface_service
    zone_service = ZoneService(
        db_factory=get_session,
        person_location_service=None,
    )
    app.state.zone_service = zone_service

    # -- Unified signals feed (cross-source caregiver alerts) -------------
    from backend.services.signals.feed import SignalsFeedService

    signals_feed_service = SignalsFeedService(db_factory=get_session)
    app.state.signals_feed = signals_feed_service

    # -- Occupancy read-model ---------------------------------------------
    # Unified live room occupancy. Fed by the world tracker (when CTS is
    # enabled) and merged-at-read with HA presence-sensor rows, so it serves
    # /occupancy regardless of whether CTS is on.
    from backend.services.occupancy import OccupancyReadModel

    occupancy_read_model = OccupancyReadModel(db_factory=get_session)
    app.state.occupancy_read_model = occupancy_read_model
