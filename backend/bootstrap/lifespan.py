"""The FastAPI lifespan: calls every bootstrap phase in the exact order
``backend/main.py`` used to construct them inline (M20).

See ``bootstrap/README.md`` for the full ``app.state`` attribute inventory,
the phase each attribute belongs to, and the handful of deviations from a
strict one-call-per-phase shape that the source's own dependency order
forced (perception sitting inside the two pipeline calls; presence being a
sub-call of ``wire_cts`` rather than a lifespan-level call).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.bootstrap import core_services, cts, guided_task, knowledge, mcp, perception, pipeline
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    core_services.wire_boot_preamble(app, settings)
    core_services.wire_core_services(app, settings)
    knowledge.wire_knowledge(app, settings)

    # -- Shared ServiceContainer ---------------------------------------------
    container, rules_engine = pipeline.wire_service_container(app, settings)

    await perception.wire_perception(app, settings, container)

    pipeline.wire_executor_and_workflow(app, settings, container, rules_engine)
    mcp.wire_mcp(app)
    scheduler_bridge = pipeline.wire_scheduler(app, settings, container, rules_engine)

    guided_camera_topology = await guided_task.wire_guided_task(
        app, settings, container, scheduler_bridge
    )

    # -- CTS gateway clients + runtime (gated by cts.enabled) --------------
    # These four attributes are set unconditionally here, then immediately
    # overwritten by whichever branch below runs -- matching main.py's own
    # pre-branch defaults (harmless: nothing reads them in between).
    # person_location_service is NOT included: perception.wire_perception
    # already constructed it unconditionally (M38 Part A), and neither
    # branch below may null it back out.
    cts_runtime = None
    app.state.ph_enrichment_service = None
    app.state.keyframe_read_service = None
    app.state.identity_correction_service = None
    app.state.reid_review_service = None
    if settings.as_bool("cts.enabled"):
        cts_runtime = await cts.wire_cts(app, settings, container, guided_camera_topology)
    else:
        cts.wire_cts_disabled(app)

    # -- PresenceService (M39 Part B: un-gated from cts.enabled) ------------
    from backend.bootstrap.presence import wire_presence

    await wire_presence(app, settings, container)

    # -- Auth: every token named at a call site must exist in auth.yaml -----
    from backend.core.auth import assert_declared_tokens_known

    assert_declared_tokens_known()

    # -- ServiceContainer completeness check (must stay last before yield) --
    from backend.services.container_wiring import assert_container_complete

    enabled_features = {"cts"} if settings.as_bool("cts.enabled") else set()
    assert_container_complete(container, enabled_features)

    # Start MCP session manager for streamable HTTP transport
    from backend.mcp.server import mcp_server

    async with mcp_server.session_manager.run():
        yield

    # -- Shutdown ----------------------------------------------------------
    app.state.scheduler.shutdown(wait=False)
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
