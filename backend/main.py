"""FastAPI application factory.

Service wiring lives in ``backend/bootstrap/`` (see
``backend/bootstrap/README.md`` for the full inventory); this module only
builds the ``FastAPI`` app, configures middleware, includes routers, and
mounts the MCP ASGI app. Importing this module performs no I/O.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.bootstrap.lifespan import lifespan
from backend.core.config import settings
from backend.core.exceptions import register_exception_handlers
from backend.schemas.misc_responses import LivenessOut


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    from backend._version import __version__

    app = FastAPI(
        title="Cognitive Companion",
        version=__version__,
        description="Privacy-first AI companion for senior care",
        lifespan=lifespan,
        # Operation IDs are the endpoint function names, so the generated TypeScript client
        # keys on `list_rules` rather than `list_rules_api_v1_rules_get` (M17). Route names
        # must therefore be unique app-wide; test_route_uniqueness.py enforces that.
        generate_unique_id_function=lambda route: route.name,
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
        cts_reid_review,
        cts_signal_evidence,
        cts_signals,
        cts_trajectory,
        cts_transit_zones,
        cts_window_triggers,
        device,
        events,
        gate_graphs,
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
    app.include_router(gate_graphs.router, prefix=api)
    app.include_router(gate_graphs.presets_router, prefix=api)
    app.include_router(guided_metrics.router, prefix=api)
    app.include_router(guided_sessions.router, prefix=api)
    app.include_router(routines.router, prefix=api)
    app.include_router(room_zones.router, prefix=api)
    app.include_router(ha_sync.router, prefix=api)
    # persons_location must precede persons: it owns the static /persons/locations path, which
    # the /persons/{person_id} route in persons.router would otherwise capture (C17).
    app.include_router(persons_location.router)  # already has /api/v1 prefix
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
    app.include_router(cts_reid_review.router, prefix=api)
    app.include_router(cts_bboxes.router, prefix=api)
    app.include_router(cts_overlap_groups.router, prefix=api)
    app.include_router(cts_diagnostics.router, prefix=api)
    app.include_router(cts_transit_zones.router, prefix=api)
    app.include_router(cts_analytics.router)  # already has /api/v1 prefix

    # WebSocket routers (no /api/v1 prefix).
    app.include_router(ws.router)
    app.include_router(cts_live.router)

    # Prometheus metrics (no auth)
    app.include_router(admin_metrics.router)

    # Health check (no auth required)
    @app.get("/api/v1/health", response_model=LivenessOut)
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
