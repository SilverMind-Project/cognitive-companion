"""Bootstrap phase: PresenceService (HaStateCache + HA providers).

Moved verbatim from ``backend/main.py``'s lifespan (M20). In the original
source this code sits *inside* the ``cts.enabled`` branch, between
``await cts_runtime.start()`` and the MCP-runtime surfacing step -- it is
not a lifespan.py-level phase call like the others. ``bootstrap.cts.wire_cts``
calls this function directly at that exact point, rather than lifespan.py
calling it, so the original nesting (presence only ever runs when CTS is
enabled, and only after the CTS runtime has started and
``app.state.person_location_service`` is set) is preserved exactly.
See ``bootstrap/README.md``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.steps.base import ServiceContainer

logger = get_logger(__name__)


async def wire_presence(app: FastAPI, settings: Settings, container: ServiceContainer) -> None:
    ha_client = app.state.ha_client

    from backend.integrations.ha_state_cache import HaStateCache
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

    providers = build_providers(
        presence_config,
        cache=ha_state_cache,
        location_service=app.state.person_location_service,
    )
    presence_service = PresenceService(
        providers=providers,
        fusion_config=presence_config.fusion,
    )
    app.state.presence = presence_service
    container.presence = presence_service
    logger.info(
        "presence_service_started",
        providers=[p.name for p in providers],
    )
