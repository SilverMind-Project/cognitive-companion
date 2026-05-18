"""Factory for building presence providers from config.

Used in ``main.py`` lifespan to instantiate the provider chain.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.ha_state_cache import HaStateCache
from backend.services.cts.location_repository import LocationRepository
from backend.services.presence.anchor_rules import compile_predicate
from backend.services.presence.config import PresenceConfig
from backend.services.presence.providers.cts_location import (
    CtsLocationProvider,
)
from backend.services.presence.providers.ha_bed_sensor import (
    HaBedSensorProvider,
)
from backend.services.presence.providers.ha_device_tracker import (
    HaDeviceTrackerProvider,
)
from backend.services.presence.providers.night_anchor import (
    NightAnchorProvider,
)
from backend.services.presence.providers.stale_fallback import (
    StaleFallbackProvider,
)
from backend.services.presence.providers.unknown import (
    UnknownProvider,
)

LocationRepositoryFactory = Callable[[], LocationRepository]

logger = get_logger(__name__)

# Mapping from config discriminator to provider class + builder.
_PROVIDER_BUILDERS: dict[str, Callable[..., Any]] = {
    "cts_location": lambda cfg, **kw: CtsLocationProvider(
        location_repository_factory=kw["location_repository_factory"],
        ttl_seconds=cfg.ttl_seconds,
        priority=cfg.priority,
    ),
    "ha_bed_sensor": lambda cfg, **kw: HaBedSensorProvider(
        cache=kw["cache"],
        entity_id=cfg.entity_id,
        person_id=cfg.person_id,
        room_id=cfg.room_id,
        room_name=cfg.room_name or cfg.room_id,
        confidence=cfg.confidence,
        priority=cfg.priority,
    ),
    "ha_device_tracker": lambda cfg, **kw: HaDeviceTrackerProvider(
        cache=kw["cache"],
        entity_id_template=cfg.entity_id_template,
        confidence=cfg.confidence,
        person_id_map=cfg.person_id_map,
        priority=cfg.priority,
    ),
    "night_anchor": lambda cfg, **kw: NightAnchorProvider(
        cache=kw["cache"],
        location_repository_factory=kw["location_repository_factory"],
        light_entities=cfg.light_entities,
        bed_sensor_entity=cfg.bed_sensor_entity,
        anchor_room_id=cfg.anchor_room_id,
        anchor_room_name=cfg.anchor_room_name,
        require_last_room_in=cfg.require_last_room_in,
        release_predicates=[
            compile_predicate(expr) for expr in cfg.release_predicates
        ],
        confidence=cfg.confidence,
        min_dark_minutes=cfg.min_dark_minutes,
        priority=cfg.priority,
    ),
    "stale_fallback": lambda cfg, **kw: StaleFallbackProvider(
        location_repository_factory=kw["location_repository_factory"],
        ttl_seconds=cfg.ttl_seconds,
        priority=cfg.priority,
    ),
    "unknown_sentinel": lambda cfg, **kw: UnknownProvider(),
}


def build_providers(
    config: PresenceConfig,
    *,
    cache: HaStateCache,
    location_repository_factory: LocationRepositoryFactory,
) -> list:  # list[PresenceProvider]
    """Build provider instances from *config*.

    Parameters
    ----------
    config:
        Validated ``PresenceConfig`` from :func:`load_presence_config`.
    cache:
        The ``HaStateCache`` for HA-backed providers.
    location_repository_factory:
        Callable returning a fresh ``LocationRepository`` per probe call.
        CTS-backed providers (``cts_location``, ``night_anchor``,
        ``stale_fallback``) use this to avoid holding a long-lived
        SQLAlchemy session.

    Returns
    -------
    list
        Provider instances sorted by ``priority`` descending.
    """
    providers: list = []  # list[PresenceProvider]

    for provider_cfg in config.providers:
        builder = _PROVIDER_BUILDERS.get(provider_cfg.name)
        if builder is None:
            raise ValueError(
                f"Unknown presence provider name {provider_cfg.name!r}. "
                f"Known: {sorted(_PROVIDER_BUILDERS)}"
            )

        provider = builder(
            provider_cfg,
            cache=cache,
            location_repository_factory=location_repository_factory,
        )
        providers.append(provider)

        # Register HA entities with the cache.
        if isinstance(provider, HaBedSensorProvider):
            provider.register()
        elif isinstance(provider, HaDeviceTrackerProvider):
            # Device tracker entities are registered per-person at
            # runtime; nothing to do here.
            pass
        elif isinstance(provider, NightAnchorProvider):
            provider.register()

    providers.sort(key=lambda p: p.priority, reverse=True)
    logger.info(
        "presence_providers_built",
        count=len(providers),
        names=[p.name for p in providers],
        priorities=[p.priority for p in providers],
    )
    return providers


def collect_required_entities(config: PresenceConfig) -> list[str]:
    """Walk *config* and return all HA entity IDs the cache must subscribe to.

    Returns entity IDs for ``ha_bed_sensor``, ``night_anchor``, and
    ``ha_device_tracker`` (resolved via a sample person_id).  CTS and
    stale providers have no HA entities.
    """
    entities: list[str] = []

    for provider_cfg in config.providers:
        if provider_cfg.name == "ha_bed_sensor":
            entities.append(provider_cfg.entity_id)
        elif provider_cfg.name == "night_anchor":
            entities.extend(provider_cfg.light_entities)
            if provider_cfg.bed_sensor_entity:
                entities.append(provider_cfg.bed_sensor_entity)
        elif provider_cfg.name == "ha_device_tracker":
            # Device tracker entities are registered per-person at
            # startup in main.py.  Here we skip them.
            pass

    return entities
