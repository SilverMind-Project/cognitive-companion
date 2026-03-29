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

    device_keys = settings.get("auth.device_keys", []) or []
    if not device_keys:
        return

    db = get_session()
    try:
        for entry in device_keys:
            sensor_id = entry.get("sensor_id")
            if not sensor_id:
                continue
            sensor_type = _DEVICE_TYPE_TO_SENSOR_TYPE.get(
                entry.get("device_type", ""), "generic"
            )
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

    # -- Realtime LLM provider (lazy – only connects when needed) ----------
    realtime_provider = None
    realtime_api_key = settings.get("llm.realtime.api_key")
    if realtime_api_key:
        from backend.integrations.llm.gemini_live import GeminiLiveProvider
        realtime_provider = GeminiLiveProvider()
    app.state.realtime_provider = realtime_provider

    # -- LLM providers for the pipeline ------------------------------------
    from backend.integrations.llm import get_provider

    vision_provider = get_provider(settings.get("llm.vision.provider"))
    logic_provider = get_provider(settings.get("llm.logic.provider"))
    translation_provider = get_provider(settings.get("llm.translation.provider"))

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

    # Placeholder callback — will be replaced once workflow is wired
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

    # -- Pipeline executor -------------------------------------------------
    from backend.services.pipeline_executor import PipelineExecutor

    pipeline_executor = PipelineExecutor(
        db_session_factory=get_session,
        person_tracking=person_tracking,
        person_id_client=person_id_client,
        vision_provider=vision_provider,
        logic_provider=logic_provider,
        translation_provider=translation_provider,
        notification_dispatcher=notifier,
        ha_client=ha_client,
        event_aggregator=event_aggregator,
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

    # -- MCP tool registry -------------------------------------------------
    from backend.mcp.server import MCPToolRegistry

    mcp_registry = MCPToolRegistry(
        db_session_factory=get_session,
        event_aggregator=event_aggregator,
        sensor_polling_service=sensor_polling,
        ha_client=ha_client,
        person_tracking=person_tracking,
    )
    app.state.mcp_registry = mcp_registry

    # -- Scheduler ---------------------------------------------------------
    from backend.services.scheduler import SchedulerBridge, setup_scheduler

    scheduler = setup_scheduler(event_aggregator, get_session, pipeline_executor)
    app.state.scheduler = scheduler

    # Inject scheduler bridge into pipeline executor for wait/resume
    scheduler_bridge = SchedulerBridge(scheduler)
    pipeline_executor._scheduler = scheduler_bridge

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

    scheduler.start()
    logger.info("Scheduler started")

    yield

    # -- Shutdown ----------------------------------------------------------
    scheduler.shutdown(wait=False)
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
        device,
        events,
        ha_sync,
        image,
        mcp,
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
    app.include_router(admin.router, prefix=api)
    app.include_router(mcp.router, prefix=api)
    app.include_router(occupancy.router, prefix=api)
    app.include_router(conversations.router, prefix=api)
    app.include_router(ha_sync.router, prefix=api)
    app.include_router(persons.router, prefix=api)
    app.include_router(workflows.router, prefix=api)
    app.include_router(activities.router, prefix=api)
    app.include_router(webhooks.router, prefix=api)
    app.include_router(pipeline.router, prefix=api)

    # WebSocket router (no /api/v1 prefix)
    app.include_router(ws.router)

    # Health check (no auth required)
    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "version": "2.0.0"}

    return app


app = create_app()
