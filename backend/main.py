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

    device_keys = settings.get("auth.device_keys")
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
    from backend.integrations.minio_client import get_minio_client
    from backend.integrations.telegram import TelegramClient
    from backend.integrations.tts import TTSClient

    minio_client = get_minio_client()
    ha_client = HomeAssistantClient()
    telegram_client = TelegramClient()
    tts_client = TTSClient()

    app.state.minio_client = minio_client
    app.state.ha_client = ha_client
    app.state.telegram_client = telegram_client
    app.state.tts_client = tts_client

    # -- WebSocket connection manager --------------------------------------
    from backend.websocket.connection_manager import ConnectionManager

    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager

    # -- Realtime LLM provider (lazy - only connects when needed) ----------
    realtime_provider = None
    realtime_api_key = settings.get("llm.realtime.api_key")
    if realtime_api_key:
        from backend.integrations.llm.gemini_live import GeminiLiveProvider

        realtime_provider = GeminiLiveProvider()
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

    # -- RAG service -------------------------------------------------------
    from backend.services.rag import RAGService

    rag_service = RAGService()
    rag_service.load()
    app.state.rag_service = rag_service
    app.state.rag_lookup = rag_service.lookup if rag_service.enabled else None

    # -- E-Ink renderer (internal integration) --------------------------------
    from backend.integrations.eink_renderer import EInkRenderer

    eink_renderer = EInkRenderer(db_session_factory=get_session)
    app.state.eink_renderer = eink_renderer

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

    # -- Person tracking service -------------------------------------------
    from backend.services.person_tracking import PersonTrackingService

    person_tracking = PersonTrackingService(
        db_session_factory=get_session,
        person_id_client=person_id_client,
        ha_client=ha_client,
        ws_manager=ws_manager,
    )
    app.state.person_tracking = person_tracking

    # -- Event aggregator --------------------------------------------------
    from backend.services.event_aggregator import EventAggregator

    # Placeholder callback  will be replaced once workflow is wired
    async def _noop_callback(sensor_id: str, media_paths: list[str]):
        pass

    aggregator_config = settings.get("event_aggregator", {})
    event_aggregator = EventAggregator(
        config=aggregator_config if isinstance(aggregator_config, dict) else {},
        db_session_factory=get_session,
        minio_client=minio_client,
        process_callback=_noop_callback,
    )
    app.state.event_aggregator = event_aggregator

    # -- Activity session service ------------------------------------------
    from backend.services.activity_session import ActivitySessionService

    activity_session_service = ActivitySessionService(get_session)
    app.state.activity_session_service = activity_session_service

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

    # -- Pipeline executor -------------------------------------------------
    from backend.services.pipeline_executor import PipelineExecutor

    pipeline_executor = PipelineExecutor(
        db_session_factory=get_session,
        person_tracking=person_tracking,
        person_id_client=person_id_client,
        notification_dispatcher=notifier,
        ha_client=ha_client,
        event_aggregator=event_aggregator,
        llm_model_registry=llm_model_registry,
        scene_analysis_client=scene_analysis_client,
        activity_session_service=activity_session_service,
        daily_report_service=daily_report_service,
        semantic_memory_client=semantic_memory_client,
        interactive_response_service=interactive_response_service,
        # scheduler bridge injected below after scheduler is created
    )
    app.state.pipeline_executor = pipeline_executor

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
        activity_timeline=activity_timeline_service,
        activity_session=activity_session_service,
        daily_report=daily_report_service,
        interactive_response=interactive_response_service,
        semantic_memory_client=semantic_memory_client,
        cts_runtime=None,  # Populated below after CTS bootstrapping.
        ws_manager=ws_manager,
    )

    # Build the Gemini tool adapter for voice tool calling
    from backend.mcp.gemini_adapter import GeminiToolAdapter

    tool_handlers, tool_schemas = get_tool_registry()
    gemini_adapter = GeminiToolAdapter(tool_handlers, tool_schemas)
    app.state.gemini_adapter = gemini_adapter

    # -- Scheduler ---------------------------------------------------------
    from backend.services.scheduler import SchedulerBridge, setup_scheduler

    scheduler = setup_scheduler(event_aggregator, get_session, pipeline_executor)
    app.state.scheduler = scheduler

    # Inject scheduler bridge into pipeline executor for wait/resume
    scheduler_bridge = SchedulerBridge(scheduler)
    pipeline_executor._scheduler = scheduler_bridge

    # Inject scheduler bridge into interactive response service
    interactive_response_service.scheduler = scheduler_bridge

    # Add HA sensor polling job
    from apscheduler.triggers.interval import IntervalTrigger

    poll_interval = settings.get("homeassistant.poll_interval_seconds", 30)
    scheduler.add_job(
        sensor_polling.poll,
        trigger=IntervalTrigger(seconds=poll_interval),
        id="poll_ha_sensors",
        name="Poll Home Assistant presence sensors",
        replace_existing=True,
    )

    # Add person tracking polling job (correlates HA presence with person IDs)
    if settings.get("person_tracking.enabled", False):
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

        tg_poll_interval = settings.get("notifications.telegram.trigger_poll_interval_seconds", 5)
        scheduler.add_job(
            telegram_trigger.poll,
            trigger=IntervalTrigger(seconds=tg_poll_interval),
            id="poll_telegram_triggers",
            name="Poll Telegram for command triggers",
            replace_existing=True,
        )
        logger.info("telegram_trigger_service_started", poll_interval_seconds=tg_poll_interval)

    scheduler.start()
    logger.info("Scheduler started")

    # -- CTS gateway clients + runtime (gated by cts.enabled) --------------
    cts_runtime = None
    if settings.get("cts.enabled", False):
        import socket

        from backend.integrations.ingress_admin_client import IngressAdminClient
        from backend.integrations.tracking_orchestrator_client import OrchestratorClient
        from backend.services.cts.runtime import CTSRuntime, CTSRuntimeConfig

        app.state.ingress_admin_client = IngressAdminClient()
        app.state.orchestrator_client = OrchestratorClient()

        redis_url = settings.get("redis.url", "redis://localhost:6379")
        consumer_id = settings.get("cts.consumer_id", socket.gethostname())
        cts_runtime = CTSRuntime(
            config=CTSRuntimeConfig(
                redis_url=redis_url,
                consumer_id=consumer_id,
                cts_lock_s=float(settings.get("cts.lock_seconds", 60)),
            ),
            db_factory=get_session,
            ws_manager=ws_manager,
            pipeline=pipeline_executor,
        )
        app.state.cts_runtime = cts_runtime
        # Expose individual subscribers for tests / diagnostics.
        app.state.dementia_signal_subscriber = cts_runtime.dementia_signal_subscriber
        app.state.tracking_event_subscriber = cts_runtime.tracking_event_subscriber
        app.state.identity_revision_subscriber = cts_runtime.identity_revision_subscriber
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

        location_repository = SqlAlchemyLocationRepository(
            cts_runtime.db_factory(),
        )
        providers = build_providers(
            presence_config,
            cache=ha_state_cache,
            location_repository=location_repository,
        )
        presence_service = PresenceService(
            providers=providers,
            fusion_config=presence_config.fusion,
        )
        app.state.presence = presence_service
        location_repository.close()
        logger.info(
            "presence_service_started",
            providers=[p.name for p in providers],
        )

        # Now that the runtime exists, surface it to the MCP tool set.
        from backend.mcp.server import _svc as _mcp_svc

        _mcp_svc.cts_runtime = cts_runtime
        logger.info("cts_runtime_started")
    else:
        app.state.ingress_admin_client = None
        app.state.orchestrator_client = None
        app.state.cts_runtime = None
        app.state.dementia_signal_subscriber = None
        app.state.tracking_event_subscriber = None
        app.state.identity_revision_subscriber = None

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
    logger.info("Shutting down Cognitive Companion v2")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Cognitive Companion",
        version="2.0.0",
        description="Privacy-first AI companion for senior care",
        lifespan=lifespan,
    )

    # CORS
    origins = settings.get("cors.origins", ["http://localhost:5173"])
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
        alerts,
        conversations,
        cts,
        cts_calibration,
        cts_cameras,
        cts_dashboard,
        cts_identity,
        cts_keyframes,
        cts_live,
        cts_presence,
        cts_signals,
        device,
        events,
        ha_sync,
        image,
        interactive_responses,
        media,
        occupancy,
        persons,
        pipeline,
        rooms,
        rules,
        sensors,
        webhooks,
        workflows,
        ws,
    )

    api = "/api/v1"
    app.include_router(rooms.router, prefix=api)
    app.include_router(sensors.router, prefix=api)
    app.include_router(rules.router, prefix=api)
    app.include_router(alerts.router, prefix=api)
    app.include_router(events.router, prefix=api)
    app.include_router(device.router, prefix=api)
    app.include_router(image.router, prefix=api)
    app.include_router(interactive_responses.router, prefix=api)
    app.include_router(media.router, prefix=api)
    app.include_router(admin.router, prefix=api)
    app.include_router(occupancy.router, prefix=api)
    app.include_router(conversations.router, prefix=api)
    app.include_router(ha_sync.router, prefix=api)
    app.include_router(persons.router, prefix=api)
    app.include_router(workflows.router, prefix=api)
    app.include_router(activities.router, prefix=api)
    app.include_router(webhooks.router, prefix=api)
    app.include_router(pipeline.router, prefix=api)
    # CTS routers: handlers return 404 when cts.enabled=false
    app.include_router(cts.router, prefix=api)
    app.include_router(cts_cameras.router, prefix=api)
    app.include_router(cts_calibration.router, prefix=api)
    app.include_router(cts_presence.router, prefix=api)
    app.include_router(cts_signals.router, prefix=api)
    app.include_router(cts_keyframes.router, prefix=api)
    app.include_router(cts_dashboard.router, prefix=api)
    app.include_router(cts_identity.router, prefix=api)

    # WebSocket routers (no /api/v1 prefix).
    app.include_router(ws.router)
    app.include_router(cts_live.router)

    # Health check (no auth required)
    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "version": "2.0.0"}

    # Mount the MCP protocol server (streamable HTTP transport)
    from backend.mcp.middleware import MCPAuthMiddleware
    from backend.mcp.server import mcp_server as _mcp_server

    _mcp_server.settings.streamable_http_path = "/"
    mcp_asgi = _mcp_server.streamable_http_app()
    app.mount("/mcp", MCPAuthMiddleware(mcp_asgi))

    return app


app = create_app()
