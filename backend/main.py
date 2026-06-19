"""FastAPI application factory with lifespan management.

Wires together all services, integrations, and routers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.database import get_session, init_db
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

# Maps device_type values (from auth.yaml) to Sensor.sensor_type values.
_DEVICE_TYPE_TO_SENSOR_TYPE: dict[str, str] = {
    "recamera": "camera",
    "reterminal": "eink",
}


def _upsert_device_key_sensors() -> None:
    """Upsert sensors for every entry in auth.yaml device_keys.

    Runs once at startup so hardware devices defined in the auth config are
    immediately queryable via the sensors API without a manual create step.
    Existing sensors are updated (name refresh); new ones are inserted.
    """
    from backend.models.sensor import Sensor

    device_keys = settings.as_list("auth.device_keys")
    if not device_keys:
        return

    db = get_session()
    try:
        for entry in device_keys:
            sensor_id = entry.get("sensor_id")
            if not sensor_id:
                continue
            sensor_type = _DEVICE_TYPE_TO_SENSOR_TYPE.get(entry.get("device_type", ""), "generic")
            name = entry.get("name", sensor_id)

            existing = db.get(Sensor, sensor_id)
            if existing:
                existing.name = name
                existing.sensor_type = sensor_type
            else:
                db.add(
                    Sensor(
                        id=sensor_id,
                        name=name,
                        sensor_type=sensor_type,
                        source="local",
                        enabled=True,
                    )
                )
        db.commit()
    except Exception:
        logger.exception("device_key_sensor_upsert_error")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    setup_logging()
    settings.reload()
    # Invalidate the auth key cache so it is rebuilt from the freshly loaded config.
    from backend.core.auth import invalidate_lookup_cache

    invalidate_lookup_cache()
    logger.info("Starting Cognitive Companion v2")

    # Database
    init_db()
    logger.info("Database initialized")

    # -- Upsert hardware devices from auth.yaml device_keys ---------------
    _upsert_device_key_sensors()
    logger.info("device_key_sensors_upserted")

    # -- Plugin discovery (steps, channels, filters) -----------------------
    from backend.channels import ChannelRegistry
    from backend.filters import FilterRegistry
    from backend.steps import StepRegistry

    StepRegistry.discover()
    ChannelRegistry.discover()
    FilterRegistry.discover()
    logger.info(
        "plugins_discovered",
        steps=StepRegistry.type_names(),
        channels=ChannelRegistry.channel_names(),
        filters=FilterRegistry.filter_types(),
    )

    # -- Integration clients -----------------------------------------------
    from backend.integrations.ha_state_cache import HaStateCache
    from backend.integrations.homeassistant import HomeAssistantClient
    from backend.integrations.minio_client import get_config_minio_client, get_minio_client
    from backend.integrations.telegram import TelegramClient
    from backend.integrations.tts import TTSClient

    minio_client = get_minio_client()
    config_minio_client = get_config_minio_client()
    ha_client = HomeAssistantClient()
    telegram_client = TelegramClient()
    tts_client = TTSClient()

    app.state.minio_client = minio_client
    app.state.config_minio_client = config_minio_client
    app.state.ha_client = ha_client
    app.state.telegram_client = telegram_client
    app.state.tts_client = tts_client

    # -- WebSocket connection manager --------------------------------------
    from backend.websocket.connection_manager import ConnectionManager
    from backend.websocket.pipeline_manager import PipelineConnectionManager

    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager

    pipeline_ws_manager = PipelineConnectionManager()
    app.state.pipeline_ws_manager = pipeline_ws_manager

    # -- Realtime LLM provider (lazy - only connects when needed) ----------
    from backend.integrations.llm.realtime import create_realtime_provider

    realtime_provider = create_realtime_provider(settings)
    app.state.realtime_provider = realtime_provider

    # -- LLM providers for the pipeline ------------------------------------
    from backend.integrations.llm import LLMModelRegistry

    # -- Named model registry (for the unified llm_call step) --------------
    llm_model_registry = LLMModelRegistry()
    llm_model_registry.load_from_settings()
    app.state.llm_model_registry = llm_model_registry
    logger.info(
        "llm_model_registry_loaded",
        models=[c.id for c in llm_model_registry.all_configs()],
    )

    # -- Conversation manager ----------------------------------------------
    from backend.services.conversation_manager import ConversationManager

    conversation_manager = ConversationManager(get_session)
    app.state.conversation_manager = conversation_manager

    # -- E-Ink renderer (internal integration) --------------------------------
    from backend.integrations.eink_renderer import EInkRenderer

    eink_renderer = EInkRenderer(db_session_factory=get_session, minio_client=config_minio_client)
    eink_renderer.seed_templates()
    app.state.eink_renderer = eink_renderer

    # -- Embedding client ---------------------------------------------------
    from backend.integrations.triton_embedding_client import TritonEmbeddingClient

    embedding_client = TritonEmbeddingClient()

    # -- Knowledge services -------------------------------------------------
    from backend.services.knowledge.content_generation import ContentGenerationService
    from backend.services.knowledge.delivery_service import KnowledgeDeliveryService
    from backend.services.knowledge.image_pipeline import ImagePipeline
    from backend.services.knowledge.ingestion_service import KnowledgeIngestionService
    from backend.services.knowledge.layout_registry import LayoutRegistry
    from backend.services.knowledge.query_service import KnowledgeQueryService
    from backend.services.knowledge.voice_instructions import VoiceInstructionConfig

    layouts_file = settings.as_str("knowledge.layouts_file")
    layout_registry = LayoutRegistry.load(layouts_file)
    app.state.layout_registry = layout_registry

    voice_config_file = settings.as_str("knowledge.voice_config_file")
    voice_instructions = VoiceInstructionConfig.load(voice_config_file)
    app.state.voice_instructions = voice_instructions

    image_pipeline = ImagePipeline(minio_client=minio_client, layouts=layout_registry)
    app.state.image_pipeline = image_pipeline

    knowledge_ingestion = KnowledgeIngestionService(
        db_factory=get_session,
        minio_client=minio_client,
        image_pipeline=image_pipeline,
        embedding_client=embedding_client,
    )
    app.state.knowledge_ingestion = knowledge_ingestion

    knowledge_query = KnowledgeQueryService(
        db_factory=get_session,
        embedding_client=embedding_client,
        llm_model_registry=llm_model_registry,
    )
    app.state.knowledge_query = knowledge_query

    knowledge_content_gen = ContentGenerationService(
        db_factory=get_session,
        llm_model_registry=llm_model_registry,
    )
    app.state.knowledge_content_gen = knowledge_content_gen

    knowledge_delivery = KnowledgeDeliveryService(
        db_factory=get_session,
        ws_manager=ws_manager,
        minio_client=minio_client,
        eink_renderer=eink_renderer,
        voice_instructions=voice_instructions,
        content_generation=knowledge_content_gen,
    )
    app.state.knowledge_delivery = knowledge_delivery

    logger.info(
        "knowledge_services_initialized",
        layouts=[lt.id for lt in layout_registry.all_layouts()],
    )

    # -- Notification dispatcher -------------------------------------------
    from backend.services.notification_dispatcher import NotificationDispatcher

    notifier = NotificationDispatcher(
        telegram_client=telegram_client,
        ws_manager=ws_manager,
        tts_client=tts_client,
        image_renderer=eink_renderer.render,
        minio_client=minio_client,
        ha_client=ha_client,
    )
    app.state.notification_dispatcher = notifier

    # -- Rules engine ------------------------------------------------------
    from backend.services.rules_engine import RulesEngine

    rules_engine = RulesEngine()

    # -- Person identification client --------------------------------------
    from backend.integrations.person_id_client import PersonIDClient

    person_id_client = PersonIDClient()
    app.state.person_id_client = person_id_client

    # -- Scene analysis client --------------------------------------------
    from backend.integrations.scene_analysis_client import SceneAnalysisClient

    scene_analysis_client = SceneAnalysisClient()
    app.state.scene_analysis_client = scene_analysis_client

    # -- Semantic memory client --------------------------------------------
    from backend.integrations.semantic_memory_client import SemanticMemoryClient

    _smc = SemanticMemoryClient()
    semantic_memory_client: SemanticMemoryClient | None = _smc if _smc.configured else None
    app.state.semantic_memory_client = semantic_memory_client

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

    # -- Scene intel service (Block 4) -------------------------------------
    from backend.services.scene_intel import SceneIntelService

    scene_intel_service = SceneIntelService(
        scene_client=scene_analysis_client,
        memory_client=semantic_memory_client,
    )
    app.state.scene_intel = scene_intel_service

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

    # -- Daily report service ----------------------------------------------
    from backend.services.daily_report import DailyReportService

    daily_report_service = DailyReportService(get_session)
    app.state.daily_report_service = daily_report_service

    # -- Interactive response service --------------------------------------
    from backend.services.interactive_response import InteractiveResponseService

    # Note: scheduler will be injected after it's created below
    interactive_response_service = InteractiveResponseService(
        db_factory=get_session,
        scheduler=None,  # Injected later
    )
    app.state.interactive_response_service = interactive_response_service

    # -- SignalsService (Block 10) -----------------------------------------
    from backend.services.signals import SignalsService

    signals_service = SignalsService(db_factory=get_session)
    app.state.signals = signals_service

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

    # -- Pipeline executor -------------------------------------------------
    from backend.services.pipeline_executor import PipelineExecutor
    from backend.services.pipeline_run_service import PipelineRunService

    pipeline_run_service = PipelineRunService(db_factory=get_session)
    app.state.pipeline_run_service = pipeline_run_service

    from backend.services.guided_task.camera_selection import CameraSourceResolverService

    camera_source_resolver = CameraSourceResolverService(get_session)
    app.state.camera_source_resolver = camera_source_resolver

    pipeline_executor = PipelineExecutor(
        db_session_factory=get_session,
        person_tracking=person_tracking,
        person_id_client=person_id_client,
        notification_dispatcher=notifier,
        ha_client=ha_client,
        event_aggregator=event_aggregator,
        llm_model_registry=llm_model_registry,
        scene_analysis_client=scene_analysis_client,
        daily_report_service=daily_report_service,
        semantic_memory_client=semantic_memory_client,
        interactive_response_service=interactive_response_service,
        memory_query=memory_query_service,
        scene_intel=scene_intel_service,
        activity=activity_service,
        signals=signals_service,
        knowledge_delivery=knowledge_delivery,
        minio_client=minio_client,
        rules_engine=rules_engine,
        event_publisher=pipeline_ws_manager.publish_event,
        camera_source_resolver=camera_source_resolver,
        # scheduler bridge injected below after scheduler is created
    )
    app.state.pipeline_executor = pipeline_executor

    # -- Media and aggregator observability --------------------------------
    from backend.services.media_observability import MediaObservabilityService

    media_observability = MediaObservabilityService(
        db_factory=get_session,
        event_aggregator=event_aggregator,
        get_bucketizer=lambda: pipeline_executor.bucketizer,
        minio_client=minio_client,
    )
    app.state.media_observability = media_observability

    # Wire pipeline executor into knowledge delivery for quiz completion resume
    knowledge_delivery._pipeline_executor = pipeline_executor

    # -- Workflow pipeline -------------------------------------------------
    from backend.services.workflow import WorkflowPipeline

    workflow = WorkflowPipeline(
        rules_engine=rules_engine,
        pipeline_executor=pipeline_executor,
    )
    app.state.workflow = workflow

    # Replace the aggregator's process callback
    async def process_event_callback(sensor_id: str, media_paths: list[str]):
        from backend.core.database import get_session as _get_session

        db = _get_session()
        try:
            await workflow.process_event(sensor_id, media_paths, "image", db)
        finally:
            db.close()

    event_aggregator._process_callback = process_event_callback

    # -- Sensor polling service --------------------------------------------
    from backend.services.sensor_polling import SensorPollingService

    sensor_polling = SensorPollingService(
        db_session_factory=get_session,
        ha_client=ha_client,
        workflow_pipeline=workflow,
    )
    app.state.sensor_polling = sensor_polling

    # -- Activity timeline service -----------------------------------------
    from backend.services.activity_timeline import ActivityTimelineService

    activity_timeline_service = ActivityTimelineService(get_session)
    app.state.activity_timeline_service = activity_timeline_service

    # -- MCP tool server (official MCP SDK) ----------------------------------
    from backend.mcp.server import get_tool_registry
    from backend.mcp.server import init_services as init_mcp_services

    init_mcp_services(
        db_session_factory=get_session,
        event_aggregator=event_aggregator,
        sensor_polling_service=sensor_polling,
        ha_client=ha_client,
        person_tracking=person_tracking,
        occupancy_read_model=occupancy_read_model,
        signals_feed=signals_feed_service,
        activity_timeline=activity_timeline_service,
        activity_session=activity_session_service,
        daily_report=daily_report_service,
        interactive_response=interactive_response_service,
        semantic_memory_client=semantic_memory_client,
        cts_runtime=None,  # Populated below after CTS bootstrapping.
        ws_manager=ws_manager,
        knowledge_query=knowledge_query,
        knowledge_delivery=knowledge_delivery,
    )

    # Build the Gemini tool adapter for voice tool calling
    from backend.mcp.gemini_adapter import GeminiToolAdapter

    tool_handlers, tool_schemas = get_tool_registry()
    gemini_adapter = GeminiToolAdapter(tool_handlers, tool_schemas)
    app.state.gemini_adapter = gemini_adapter

    # -- Scheduler ---------------------------------------------------------
    from backend.services.scheduler import SchedulerBridge, setup_scheduler

    scheduler = setup_scheduler(
        event_aggregator, get_session, pipeline_executor, rules_engine=rules_engine
    )
    app.state.scheduler = scheduler

    # Inject scheduler bridge into pipeline executor for wait/resume
    scheduler_bridge = SchedulerBridge(scheduler)
    pipeline_executor._scheduler = scheduler_bridge

    # Inject scheduler bridge into interactive response service
    interactive_response_service.scheduler = scheduler_bridge

    # -- Guided task service (headless M3 runtime) -------------------------
    from backend.mcp.server import set_guided_task_service
    from backend.services.guided_task import (
        AgentSessionVoice,
        FullEscalator,
        GuidedMetricsService,
        GuidedTaskSafetyWatch,
        GuidedTaskService,
        SensorRoomCameraTopology,
    )

    guided_camera_topology = SensorRoomCameraTopology(get_session)
    guided_safety_watch = GuidedTaskSafetyWatch(
        db_factory=get_session,
        person_location_service=None,
        zone_service=zone_service,
        bucketizer=None,
        camera_topology=guided_camera_topology,
        identity_resolver=lambda person_id: {person_id},
        scene_analysis_client=scene_analysis_client,
        signals_service=signals_service,
        minio_client=minio_client,
        settings=settings,
    )
    from backend.services.guided_task.gate_runner import GateGraphRunner

    gate_runner = GateGraphRunner(
        services=pipeline_executor._services,
        db_factory=get_session,
        settings=settings,
    )
    app.state.gate_runner = gate_runner

    guided_task_service = GuidedTaskService(
        db_factory=get_session,
        scheduler=scheduler_bridge,
        pipeline_executor=pipeline_executor,
        zone_service=zone_service,
        bucketizer=None,
        camera_topology=guided_camera_topology,
        llm_model_registry=llm_model_registry,
        minio_client=minio_client,
        activity_service=activity_service,
        signals_service=signals_service,
        scene_analysis_client=scene_analysis_client,
        companion_surface_service=companion_surface_service,
        ws_manager=ws_manager,
        admin_ws_broadcaster=pipeline_ws_manager.broadcast,
        notification_dispatcher=notifier,
        conversation_manager=conversation_manager,
        semantic_memory_client=semantic_memory_client,
        memory_query=memory_query_service,
        voice=AgentSessionVoice(
            ws_manager=ws_manager,
            voice_instructions=voice_instructions,
            memory_query=memory_query_service,
        ),
        escalator=FullEscalator(
            notifier,
            db_factory=get_session,
            ws_manager=ws_manager,
            admin_ws_broadcaster=pipeline_ws_manager.broadcast,
            conversation_manager=conversation_manager,
            settings=settings,
        ),
        safety_watch=guided_safety_watch,
        settings=settings,
        gate_runner=gate_runner,
        camera_source_resolver=camera_source_resolver,
        event_aggregator=event_aggregator,
    )
    app.state.guided_task_service = guided_task_service
    set_guided_task_service(guided_task_service)
    pipeline_executor._services.guided_task = guided_task_service
    guided_metrics_service = GuidedMetricsService(db_factory=get_session, settings=settings)
    app.state.guided_metrics_service = guided_metrics_service
    from backend.mcp.server import set_guided_metrics_service

    set_guided_metrics_service(guided_metrics_service)

    # Add HA sensor polling job
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        guided_task_service.tick,
        trigger=IntervalTrigger(seconds=settings.as_int("guided_task.safety_tick_s")),
        id="guided_task_safety_tick",
        name="Guided task safety watch tick",
        replace_existing=True,
    )

    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        guided_task_service.prune_retained_data,
        trigger=CronTrigger(hour=3, minute=20, timezone=ZoneInfo(settings.as_str("app.timezone"))),
        id="guided_task_retention_prune",
        name="Prune guided task retained transcripts and events",
        replace_existing=True,
    )

    poll_interval = settings.as_int("homeassistant.poll_interval_seconds")
    scheduler.add_job(
        sensor_polling.poll,
        trigger=IntervalTrigger(seconds=poll_interval),
        id="poll_ha_sensors",
        name="Poll Home Assistant presence sensors",
        replace_existing=True,
    )

    # Add person tracking polling job (correlates HA presence with person IDs)
    if settings.as_bool("person_tracking.enabled"):
        scheduler.add_job(
            person_tracking.poll_ha_presence_sensors,
            trigger=IntervalTrigger(seconds=poll_interval),
            id="poll_person_tracking",
            name="Correlate HA presence with person tracking",
            replace_existing=True,
        )

    # Add conversation pruning job
    scheduler.add_job(
        conversation_manager.prune_old_turns,
        trigger=IntervalTrigger(minutes=30),
        id="prune_conversations",
        name="Prune old conversation turns",
        replace_existing=True,
    )

    # -- Telegram trigger service (command-to-rule polling) ----------------
    if telegram_client.configured:
        from backend.services.telegram_trigger import TelegramTriggerService

        telegram_trigger = TelegramTriggerService(
            telegram_client=telegram_client,
            pipeline_executor=pipeline_executor,
            db_session_factory=get_session,
        )
        app.state.telegram_trigger = telegram_trigger

        await telegram_client.setup_polling()

        tg_poll_interval = settings.as_int("notifications.telegram.trigger_poll_interval_seconds")
        scheduler.add_job(
            telegram_trigger.poll,
            trigger=IntervalTrigger(seconds=tg_poll_interval),
            id="poll_telegram_triggers",
            name="Poll Telegram for command triggers",
            replace_existing=True,
        )
        logger.info("telegram_trigger_service_started", poll_interval_seconds=tg_poll_interval)

    # -- Knowledge re-embed retry job (Phase 5) --------------------------
    scheduler.add_job(
        knowledge_ingestion.reembed_stuck_documents,
        trigger=IntervalTrigger(minutes=10),
        id="knowledge_reembed_retry",
        name="Retry embedding for documents stuck in uploaded status",
        replace_existing=True,
    )
    logger.info("knowledge_reembed_job_scheduled", interval_minutes=10)

    scheduler.start()
    logger.info("Scheduler started")

    # -- CTS gateway clients + runtime (gated by cts.enabled) --------------
    cts_runtime = None
    app.state.ph_enrichment_service = None
    app.state.person_location_service = None
    if settings.as_bool("cts.enabled"):
        from backend.integrations.ingress_admin_client import IngressAdminClient
        from backend.integrations.tracking_orchestrator_client import OrchestratorClient
        from backend.services.cts.event_bucketizer import BucketizerRateConfig
        from backend.services.cts.ph_enrichment import PHEnrichmentService
        from backend.services.cts.runtime import CTSRuntime, CTSRuntimeConfig
        from backend.services.person_location.repositories import (
            SqlAlchemyObservationRepository,
            SqlAlchemySegmentRepository,
        )
        from backend.services.person_location.service import PersonLocationService

        app.state.ingress_admin_client = IngressAdminClient()
        app.state.orchestrator_client = OrchestratorClient()
        app.state.ph_enrichment_service = PHEnrichmentService(app.state.orchestrator_client)

        from backend.services.gait_trend_service import GaitTrendService

        gait_trend_service = GaitTrendService(app.state.orchestrator_client)
        app.state.gait_trend_service = gait_trend_service

        redis_url = settings.as_str("redis.url", allow_empty=False)
        consumer_id = settings.as_str("cts.consumer_id", allow_empty=False)

        # PersonLocationService with session-aware repos.
        # Each repo method opens a short-lived session via the factory,
        # committing and closing after each operation so that TimescaleDB
        # chunk-creation locks are never held across idle periods.
        def _make_pls() -> PersonLocationService:
            return PersonLocationService(
                obs_repo=SqlAlchemyObservationRepository(get_session),
                seg_repo=SqlAlchemySegmentRepository(get_session),
            )

        person_location_service = _make_pls()
        app.state.person_location_service = person_location_service
        companion_surface_service.set_person_location_service(person_location_service)
        zone_service.set_person_location_service(person_location_service)
        guided_task_service.set_person_location_service(person_location_service)

        # M4 subscribers (world-observation, room-transition, ph-continuation)
        # are constructed and owned by CTSRuntime, which wires the camera→room
        # id map and occupancy read-model the world tracker needs.
        cts_settings = settings.as_dict("cts")
        cts_runtime = CTSRuntime(
            config=CTSRuntimeConfig(
                redis_url=redis_url,
                consumer_id=consumer_id,
                cts_lock_s=settings.as_float("cts.lock_seconds"),
                bucketizer_rate=BucketizerRateConfig.model_validate(
                    {
                        "image_rate_per_second": cts_settings.get("image_rate_per_second", 0.5),
                        "image_rate_burst": cts_settings.get("image_rate_burst", 2.0),
                        "image_rate_overrides": cts_settings.get("image_rate_overrides", {}),
                    }
                ),
            ),
            db_factory=get_session,
            ws_manager=ws_manager,
            pipeline=pipeline_executor,
            minio_client=minio_client,
            scene_analysis_client=scene_analysis_client,
            semantic_memory_client=semantic_memory_client,
            authority=shared_authority,
            person_location_service=person_location_service,
            occupancy_read_model=occupancy_read_model,
        )
        app.state.cts_runtime = cts_runtime
        # Give the pipeline executor access to the CTS frame buffer so the
        # canonical media poll step and its CTS alias can return recent frames.
        # The bucketizer is built after the executor, so inject it here.
        pipeline_executor.bucketizer = cts_runtime.bucketizer
        guided_task_service.set_bucketizer(cts_runtime.bucketizer)
        guided_task_service.set_safety_watch(
            GuidedTaskSafetyWatch(
                db_factory=get_session,
                person_location_service=person_location_service,
                zone_service=zone_service,
                bucketizer=cts_runtime.bucketizer,
                camera_topology=guided_camera_topology,
                identity_resolver=lambda person_id: {person_id},
                scene_analysis_client=scene_analysis_client,
                signals_service=signals_service,
                minio_client=minio_client,
                settings=settings,
            )
        )
        # Expose individual subscribers for tests / diagnostics.
        app.state.dementia_signal_subscriber = cts_runtime.dementia_signal_subscriber
        app.state.tracking_event_subscriber = cts_runtime.tracking_event_subscriber
        app.state.identity_revision_subscriber = cts_runtime.identity_revision_subscriber
        app.state.scene_sample_subscriber = cts_runtime.scene_sample_subscriber
        await cts_runtime.start()

        # -- PresenceService (Block 2: HaStateCache + HA providers) --------
        from pathlib import Path

        from backend.services.cts.location_repository import (
            SqlAlchemyLocationRepository,
        )
        from backend.services.presence import PresenceService
        from backend.services.presence.config import load_presence_config
        from backend.services.presence.factory import (
            build_providers,
            collect_required_entities,
        )

        presence_config = load_presence_config(Path("config/presence.yaml"))
        ha_state_cache = HaStateCache(homeassistant_client=ha_client)
        for entity in collect_required_entities(presence_config):
            ha_state_cache.register(entity)
        await ha_state_cache.start()
        app.state.ha_state_cache = ha_state_cache

        def _location_repo_factory() -> SqlAlchemyLocationRepository:
            return SqlAlchemyLocationRepository(cts_runtime._db_factory())

        providers = build_providers(
            presence_config,
            cache=ha_state_cache,
            location_repository_factory=_location_repo_factory,
        )
        presence_service = PresenceService(
            providers=providers,
            fusion_config=presence_config.fusion,
        )
        app.state.presence = presence_service
        logger.info(
            "presence_service_started",
            providers=[p.name for p in providers],
        )

        # Now that the runtime exists, surface it to the MCP tool set.
        from backend.mcp.server import _svc as _mcp_svc

        _mcp_svc.cts_runtime = cts_runtime
        _mcp_svc.person_location_service = person_location_service
        _mcp_svc.gait_trend_service = gait_trend_service
        logger.info("cts_runtime_started")

        # -- Drift detection poll (M11) -------------------------------------
        from functools import partial

        from backend.services.cts.drift_poll import poll_camera_drift

        drift_poll_interval_s = int(settings.get("cts.drift_poll_interval_s") or 3600)
        _orchestrator_client = app.state.orchestrator_client
        scheduler.add_job(
            partial(
                poll_camera_drift,
                db_factory=get_session,
                orchestrator=_orchestrator_client,
            ),
            trigger=IntervalTrigger(seconds=drift_poll_interval_s),
            id="cts_drift_poll",
            name="CTS camera drift detection poll",
            replace_existing=True,
        )
        logger.info("cts_drift_poll_scheduled", interval_s=drift_poll_interval_s)
    else:
        app.state.ingress_admin_client = None
        app.state.orchestrator_client = None
        app.state.ph_enrichment_service = None
        app.state.cts_runtime = None
        app.state.dementia_signal_subscriber = None
        app.state.tracking_event_subscriber = None
        app.state.identity_revision_subscriber = None
        app.state.person_location_service = None
        app.state.gait_trend_service = None

    # Start MCP session manager for streamable HTTP transport
    from backend.mcp.server import mcp_server

    async with mcp_server.session_manager.run():
        yield

    # -- Shutdown ----------------------------------------------------------
    scheduler.shutdown(wait=False)
    if cts_runtime is not None:
        await cts_runtime.stop()
    if app.state.ha_state_cache is not None:
        await app.state.ha_state_cache.stop()
    # Close integration HTTP clients (connection pools)
    if hasattr(app.state, "scene_analysis_client") and app.state.scene_analysis_client is not None:
        await app.state.scene_analysis_client.close()
    if (
        hasattr(app.state, "semantic_memory_client")
        and app.state.semantic_memory_client is not None
    ):
        await app.state.semantic_memory_client.close()
    logger.info("Shutting down Cognitive Companion v2")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    from backend._version import __version__

    app = FastAPI(
        title="Cognitive Companion",
        version=__version__,
        description="Privacy-first AI companion for senior care",
        lifespan=lifespan,
    )

    # CORS
    origins = settings.as_list("cors.origins")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    register_exception_handlers(app)

    # -- API Routers -------------------------------------------------------
    from backend.routers import (
        activities,
        admin,
        admin_metrics,
        companion_surfaces,
        conversations,
        cts,
        cts_analytics,
        cts_bboxes,
        cts_calibration,
        cts_calibration_health,
        cts_cameras,
        cts_dashboard,
        cts_diagnostics,
        cts_gait,
        cts_keyframes,
        cts_live,
        cts_overlap_groups,
        cts_ph,
        cts_presence,
        cts_presence_timeline,
        cts_signal_evidence,
        cts_signals,
        cts_trajectory,
        cts_transit_zones,
        cts_window_triggers,
        device,
        events,
        guided_metrics,
        guided_sessions,
        ha_sync,
        household,
        image,
        info_cards,
        interactive_responses,
        knowledge,
        knowledge_interactions,
        knowledge_layouts,
        media,
        occupancy,
        persons,
        persons_location,
        pipeline,
        pipeline_images,
        pipeline_runs,
        quizzes,
        room_zones,
        rooms,
        routines,
        rules,
        sensors,
        signals_feed,
        webhooks,
        workflows,
        ws,
    )

    api = "/api/v1"
    app.include_router(rooms.router, prefix=api)
    app.include_router(household.router, prefix=api)
    app.include_router(sensors.router, prefix=api)
    app.include_router(rules.router, prefix=api)
    app.include_router(cts_window_triggers.router, prefix=api)
    app.include_router(signals_feed.router, prefix=api)
    app.include_router(events.router, prefix=api)
    app.include_router(device.router, prefix=api)
    app.include_router(image.router, prefix=api)
    app.include_router(interactive_responses.router, prefix=api)
    app.include_router(media.router, prefix=api)
    app.include_router(admin.router, prefix=api)
    app.include_router(occupancy.router, prefix=api)
    app.include_router(conversations.router, prefix=api)
    app.include_router(companion_surfaces.router, prefix=api)
    app.include_router(guided_metrics.router, prefix=api)
    app.include_router(guided_sessions.router, prefix=api)
    app.include_router(routines.router, prefix=api)
    app.include_router(room_zones.router, prefix=api)
    app.include_router(ha_sync.router, prefix=api)
    app.include_router(persons.router, prefix=api)
    app.include_router(workflows.router, prefix=api)
    app.include_router(activities.router, prefix=api)
    app.include_router(webhooks.router, prefix=api)
    app.include_router(pipeline.router, prefix=api)
    app.include_router(pipeline_images.router, prefix=api)
    app.include_router(pipeline_runs.router, prefix=api)
    # Knowledge repository routers
    app.include_router(knowledge.router, prefix=api)
    app.include_router(info_cards.router, prefix=api)
    app.include_router(quizzes.router, prefix=api)
    app.include_router(knowledge_interactions.router, prefix=api)
    app.include_router(knowledge_interactions.analytics_router, prefix=api)
    app.include_router(knowledge_layouts.router, prefix=api)
    app.include_router(knowledge_layouts.voice_defaults_router, prefix=api)
    # CTS routers: handlers return 404 when cts.enabled=false
    app.include_router(cts.router, prefix=api)
    app.include_router(cts_cameras.router, prefix=api)
    app.include_router(cts_calibration.router, prefix=api)
    app.include_router(cts_calibration_health.router, prefix=api)
    app.include_router(cts_presence.router, prefix=api)
    app.include_router(cts_presence_timeline.router, prefix=api)
    app.include_router(cts_signal_evidence.router, prefix=api)
    app.include_router(cts_signals.router, prefix=api)
    app.include_router(cts_trajectory.router, prefix=api)
    app.include_router(cts_keyframes.router, prefix=api)
    app.include_router(cts_dashboard.router, prefix=api)
    app.include_router(cts_gait.router, prefix=api)
    app.include_router(cts_ph.router, prefix=api)
    app.include_router(cts_bboxes.router, prefix=api)
    app.include_router(cts_overlap_groups.router, prefix=api)
    app.include_router(cts_diagnostics.router, prefix=api)
    app.include_router(cts_transit_zones.router, prefix=api)
    app.include_router(cts_analytics.router)  # already has /api/v1 prefix
    app.include_router(persons_location.router)  # already has /api/v1 prefix

    # WebSocket routers (no /api/v1 prefix).
    app.include_router(ws.router)
    app.include_router(cts_live.router)

    # Prometheus metrics (no auth)
    app.include_router(admin_metrics.router)

    # Health check (no auth required)
    @app.get("/api/v1/health")
    async def health():
        from backend._version import __version__

        return {"status": "ok", "version": __version__}

    # Mount the MCP protocol server (streamable HTTP transport)
    from backend.mcp.middleware import MCPAuthMiddleware
    from backend.mcp.server import mcp_server as _mcp_server

    _mcp_server.settings.streamable_http_path = "/"
    mcp_asgi = _mcp_server.streamable_http_app()
    app.mount("/mcp", MCPAuthMiddleware(mcp_asgi))

    return app


app = create_app()
