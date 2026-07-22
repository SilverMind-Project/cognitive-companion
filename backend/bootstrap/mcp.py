"""Bootstrap phase: MCP tool registry + Gemini tool adapter.

Moved verbatim from ``backend/main.py``'s lifespan (M20). Named ``mcp.py``
per the M20 milestone; this is a different dotted path from the top-level
``backend.mcp`` package it wires (``backend.bootstrap.mcp`` vs
``backend.mcp``), so there is no import collision.

The ``/mcp`` ASGI mount and its auth middleware are *not* here: FastAPI
mounts must be registered synchronously while the app object is being
built, not from the async lifespan, so they stay in ``backend/main.py``'s
``create_app()``. See ``bootstrap/README.md``.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.core.database import get_session


def wire_mcp(app: FastAPI) -> None:
    # -- MCP tool server (official MCP SDK) ----------------------------------
    from backend.mcp.server import get_tool_registry
    from backend.mcp.server import init_services as init_mcp_services

    init_mcp_services(
        db_session_factory=get_session,
        event_aggregator=app.state.event_aggregator,
        sensor_polling_service=app.state.sensor_polling,
        ha_client=app.state.ha_client,
        person_tracking=app.state.person_tracking,
        occupancy_read_model=app.state.occupancy_read_model,
        signals_feed=app.state.signals_feed,
        activity_timeline=app.state.activity_timeline_service,
        activity_session=app.state.activity_session_service,
        daily_report=app.state.daily_report_service,
        interactive_response=app.state.interactive_response_service,
        semantic_memory_client=app.state.semantic_memory_client,
        cts_runtime=None,  # Populated below after CTS bootstrapping.
        ws_manager=app.state.ws_manager,
        knowledge_query=app.state.knowledge_query,
        knowledge_delivery=app.state.knowledge_delivery,
        knowledge_ingestion=app.state.knowledge_ingestion,
    )

    # Build the Gemini tool adapter for voice tool calling
    from backend.mcp.gemini_adapter import GeminiToolAdapter

    tool_handlers, tool_schemas = get_tool_registry()
    gemini_adapter = GeminiToolAdapter(tool_handlers, tool_schemas)
    app.state.gemini_adapter = gemini_adapter
