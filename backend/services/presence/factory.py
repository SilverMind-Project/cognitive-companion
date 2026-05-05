"""Factory for building presence providers from config.

Used in ``main.py`` lifespan to instantiate the provider chain.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.ha_state_cache import HaStateCache
from backend.services.cts.location_repository import LocationRepository
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

logger = get_logger(__name__)

# Mapping from config discriminator to provider class + builder.
_PROVIDER_BUILDERS: dict[str, Callable[..., Any]] = {
    "cts_location": lambda cfg, **kw: CtsLocationProvider(
        location_repository=kw["location_repository"],
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
}


def build_providers(
    config: PresenceConfig,
    *,
    cache: HaStateCache,
    location_repository: LocationRepository,
) -> list:  # list[PresenceProvider]
    """Build provider instances from *config*.

    Parameters
    ----------
    config:
        Validated ``PresenceConfig`` from :func:`load_presence_config`.
    cache:
        The ``HaStateCache`` for HA-backed providers.
    location_repository:
        The ``LocationRepository`` for CTS-backed providers.

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
            location_repository=location_repository,
        )
        providers.append(provider)

        # Register HA entities with the cache.
        if isinstance(provider, HaBedSensorProvider):
            provider.register()
        elif isinstance(provider, HaDeviceTrackerProvider):
            # Device tracker entities are registered per-person at
            # runtime; nothing to do here.
            pass

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

    Returns entity IDs for ``ha_bed_sensor`` and ``ha_device_tracker``
    (resolved via a sample person_id).  CTS provider has no HA entities.
    """
    entities: list[str] = []

    for provider_cfg in config.providers:
        if provider_cfg.name == "ha_bed_sensor":
            entities.append(provider_cfg.entity_id)
        elif provider_cfg.name == "ha_device_tracker":
            # We need at least one person_id to resolve the template.
            # The actual per-person registration happens at startup in
            # main.py after we know all enrolled persons.  Here we
            # return the template string itself as a placeholder;
            # callers should expand it.
            # For now, skip device_tracker entities here -- they are
            # registered dynamically in main.py.
            pass

    return entities
