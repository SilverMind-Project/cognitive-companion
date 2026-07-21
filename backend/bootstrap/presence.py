"""Bootstrap phase: PresenceService (HaStateCache + HA providers).

M39 Part B: presence service construction is un-gated from ``cts.enabled``:
it runs unconditionally in ``lifespan.py`` after the CTS branch, because
presence reads from ``PersonLocationService`` (SSOT) and ``HaStateCache``,
neither of which depends on CTS.
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
    # The TV media_player entity backs the home_state filter/step's
    # entity_id extension used by the watching_tv activity-ledger rules.
    tv_entity = settings.get("daily_living.tv.media_player_entity", "")
    if tv_entity:
        ha_state_cache.register(tv_entity)
    await ha_state_cache.start()
    app.state.ha_state_cache = ha_state_cache
    container.ha_state_cache = ha_state_cache

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
