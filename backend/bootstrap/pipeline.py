"""Bootstrap phase: shared ServiceContainer, rules engine, pipeline executor,
workflow pipeline, and scheduler bridge wiring.

Moved verbatim from ``backend/main.py``'s lifespan (M20). Split into three
functions because ``bootstrap.perception`` and ``bootstrap.mcp`` sit
between them in the original construction order (perception populates
container fields the executor reads; the MCP tool registry is built before
the scheduler in the source) -- see ``bootstrap/README.md`` for the full
call sequence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.database import get_session
from backend.core.logging import get_logger
from backend.steps.base import ServiceContainer

if TYPE_CHECKING:
    from backend.services.rules_engine import RulesEngine
    from backend.services.scheduler import SchedulerBridge

logger = get_logger(__name__)


def wire_service_container(
    app: FastAPI, settings: Settings
) -> tuple[ServiceContainer, RulesEngine]:
    """Build the shared ``ServiceContainer`` and the rules engine.

    Built once, here, with every service available at this point in the
    lifespan. Later phases assign onto this same instance as they come up
    (never rebuilt) so the executor, gate runner, and rules engine -- all
    constructed later -- see late-phase services automatically.
    """
    from backend.services.rules_engine import RulesEngine

    services_container = ServiceContainer(
        db_factory=get_session,
        notification_dispatcher=app.state.notification_dispatcher,
        ha_client=app.state.ha_client,
        llm_model_registry=app.state.llm_model_registry,
        minio_client=app.state.minio_client,
        knowledge_delivery=app.state.knowledge_delivery,
    )
    app.state.service_container = services_container

    # -- Rules engine ------------------------------------------------------
    rules_engine = RulesEngine(services_container)

    return services_container, rules_engine


def wire_executor_and_workflow(
    app: FastAPI, settings: Settings, container: ServiceContainer, rules_engine: RulesEngine
) -> None:
    """Pipeline executor, media observability, workflow pipeline, sensor
    polling, activity timeline."""
    pipeline_ws_manager = app.state.pipeline_ws_manager
    event_aggregator = app.state.event_aggregator
    minio_client = app.state.minio_client
    knowledge_delivery = app.state.knowledge_delivery
    ha_client = app.state.ha_client

    # -- Pipeline executor -------------------------------------------------
    from backend.services.pipeline_executor import PipelineExecutor
    from backend.services.pipeline_run_service import PipelineRunService

    pipeline_run_service = PipelineRunService(db_factory=get_session)
    app.state.pipeline_run_service = pipeline_run_service

    from backend.services.guided_task.camera_selection import CameraSourceResolverService

    camera_source_resolver = CameraSourceResolverService(get_session)
    app.state.camera_source_resolver = camera_source_resolver
    container.camera_source_resolver = camera_source_resolver

    pipeline_executor = PipelineExecutor(
        container,
        rules_engine=rules_engine,
        event_publisher=pipeline_ws_manager.publish_event,
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


def wire_scheduler(
    app: FastAPI, settings: Settings, container: ServiceContainer, rules_engine: RulesEngine
) -> SchedulerBridge:
    """Construct the APScheduler instance and its executor/interactive-response
    bridge. Job registration and ``scheduler.start()`` happen in
    ``bootstrap.guided_task`` -- see that module's docstring for why."""
    event_aggregator = app.state.event_aggregator
    pipeline_executor = app.state.pipeline_executor
    interactive_response_service = app.state.interactive_response_service

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

    return scheduler_bridge
