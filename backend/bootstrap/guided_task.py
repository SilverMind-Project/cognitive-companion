"""Bootstrap phase: guided-task runtime + every APScheduler job registration.

Moved verbatim from ``backend/main.py``'s lifespan (M20): the guided-task
safety watch, ``GateGraphRunner``, ``GuidedTaskService``, the metrics
service, and -- because they are textually interleaved with guided-task
construction in the original source and moving them apart would mean
reordering statements, which a behavior-preserving refactor may not do --
every ``scheduler.add_job`` call, the telegram trigger service, and
``scheduler.start()``. See ``bootstrap/README.md`` for the exact source
line range and the reasoning.

M38 Part A also moved the person-location inferred-dwell/quiet-gap tick
job here as a scheduler ``add_job`` (previously an asyncio task owned by
``CTSRuntime`` and only running when ``cts.enabled``), since this module
already owns every unconditional job registration.

Wave-3 addendum note: the two private reach-ins the wave-3 M20 addendum
flagged (``GateGraphRunner(services=pipeline_executor._services, ...)`` and
``pipeline_executor._services.guided_task = ...``) were already resolved by
M13 before this refactor started -- current ``main.py`` passes the shared
``container`` directly and assigns ``container.guided_task`` -- so both
move verbatim with no further change here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.steps.base import ServiceContainer

if TYPE_CHECKING:
    from backend.services.guided_task.camera_selection import SensorRoomCameraTopology
    from backend.services.scheduler import SchedulerBridge

logger = get_logger(__name__)


async def wire_guided_task(
    app: FastAPI,
    settings: Settings,
    container: ServiceContainer,
    scheduler_bridge: SchedulerBridge,
) -> SensorRoomCameraTopology:
    zone_service = app.state.zone_service
    scene_analysis_client = app.state.scene_analysis_client
    signals_service = app.state.signals
    minio_client = app.state.minio_client
    pipeline_executor = app.state.pipeline_executor
    llm_model_registry = app.state.llm_model_registry
    activity_service = app.state.activity_service
    companion_surface_service = app.state.companion_surface_service
    ws_manager = app.state.ws_manager
    pipeline_ws_manager = app.state.pipeline_ws_manager
    notifier = app.state.notification_dispatcher
    conversation_manager = app.state.conversation_manager
    memory_query_service = app.state.memory_query
    voice_instructions = app.state.voice_instructions
    camera_source_resolver = app.state.camera_source_resolver
    event_aggregator = app.state.event_aggregator
    scheduler = app.state.scheduler
    sensor_polling = app.state.sensor_polling
    person_tracking = app.state.person_tracking
    telegram_client = app.state.telegram_client
    knowledge_ingestion = app.state.knowledge_ingestion
    embedding_client = app.state.embedding_client
    scene_intel = app.state.scene_intel
    person_location_service = app.state.person_location_service

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
        services=container,
        db_factory=get_session,
        settings=settings,
    )
    app.state.gate_runner = gate_runner

    guided_task_service = GuidedTaskService(
        db_factory=get_session,
        scheduler=scheduler_bridge,
        pipeline_executor=pipeline_executor,
        person_location_service=person_location_service,
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
        memory_query=memory_query_service,
        scene_intel=scene_intel,
        embedding_client=embedding_client,
        knowledge_ingestion=knowledge_ingestion,
        voice=AgentSessionVoice(
            ws_manager=ws_manager,
            voice_instructions=voice_instructions,
            memory_query=memory_query_service,
            settings=settings,
        ),
        voice_instructions=voice_instructions,
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
    container.guided_task = guided_task_service
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

    # -- Person-location tick: inferred-dwell timeout +
    # per-source quiet-gap segment closure. Previously an asyncio task owned
    # by CTSRuntime (only running when cts.enabled); now on the shared
    # scheduler since PersonLocationService is always constructed.
    from backend.services.cts.signal_store import SignalStore

    _PERSON_LOCATION_TICK_INTERVAL_S = 60

    async def _run_person_location_tick() -> None:
        from datetime import UTC
        from datetime import datetime as dt

        signals = await person_location_service.tick(dt.now(UTC))
        if not signals:
            return
        store = SignalStore(db_factory=get_session)
        for sig in signals:
            await store.upsert(sig)
            logger.info(
                "inferred_dwell_signal_persisted",
                person_id=sig.get("person_id"),
                signal_type=sig.get("signal_type"),
            )

    scheduler.add_job(
        _run_person_location_tick,
        trigger=IntervalTrigger(seconds=_PERSON_LOCATION_TICK_INTERVAL_S),
        id="person_location_tick",
        name="Person-location inferred-dwell timeout and quiet-segment closure",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")

    return guided_camera_topology
