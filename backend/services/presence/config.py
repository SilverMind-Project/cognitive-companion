"""Presence service configuration loading.

Parses ``config/presence.yaml`` into typed Pydantic models so the
factory can instantiate providers from config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field

# -- Provider configs --------------------------------------------------------


class CtsLocationProviderConfig(BaseModel):
    """CTS location provider config."""

    name: Literal["cts_location"] = "cts_location"
    confidence_floor: float = 0.0
    ttl_seconds: int = 120
    priority: int = 50


class HaBedSensorProviderConfig(BaseModel):
    """HA bed-sensor provider config."""

    name: Literal["ha_bed_sensor"]
    entity_id: str
    person_id: str
    room_id: str
    room_name: str | None = None
    confidence: float = 0.95
    priority: int = 70


class HaDeviceTrackerProviderConfig(BaseModel):
    """HA device-tracker provider config."""

    name: Literal["ha_device_tracker"]
    entity_id_template: str
    confidence: float = 0.8
    person_id_map: dict[str, str] | None = None
    priority: int = 30


class NightAnchorProviderConfig(BaseModel):
    """Night-anchor provider config (Block 3)."""

    name: Literal["night_anchor"] = "night_anchor"
    light_entities: list[str]
    bed_sensor_entity: str
    anchor_room_id: str
    anchor_room_name: str
    require_last_room_in: list[str]
    release_predicates: list[str] = Field(default_factory=list)
    confidence: float = 0.95
    min_dark_minutes: int = 10
    priority: int = 90


class StaleFallbackProviderConfig(BaseModel):
    """Stale-fallback provider config (Block 3)."""

    name: Literal["stale_fallback"] = "stale_fallback"
    ttl_seconds: int = 3600
    priority: int = 10


class UnknownSentinelProviderConfig(BaseModel):
    """Unknown-sentinel provider config (Block 3)."""

    name: Literal["unknown_sentinel"] = "unknown_sentinel"


Provider = Annotated[
    CtsLocationProviderConfig
    | HaBedSensorProviderConfig
    | HaDeviceTrackerProviderConfig
    | NightAnchorProviderConfig
    | StaleFallbackProviderConfig
    | UnknownSentinelProviderConfig,
    Field(discriminator="name"),
]


# -- Fusion config -----------------------------------------------------------


class FusionConfig(BaseModel):
    """Fusion rule configuration."""

    rule: Literal["highest_priority_above_floor"] = (
        "highest_priority_above_floor"
    )
    confidence_floor: float = 0.4


# -- Top-level config --------------------------------------------------------


class PresenceConfig(BaseModel):
    """Top-level presence service configuration."""

    providers: list[Provider]
    fusion: FusionConfig = Field(default_factory=FusionConfig)


# -- Loading -----------------------------------------------------------------


def load_presence_config(path: Path | str = "config/presence.yaml") -> PresenceConfig:
    """Parse and validate a presence config YAML file.

    Parameters
    ----------
    path:
        Filesystem path to the YAML file.  Defaults to
        ``config/presence.yaml`` relative to the working directory.

    Returns
    -------
    PresenceConfig
        Validated configuration object.

    Raises
    ------
    ValueError
        When the YAML contains an unknown provider ``name``.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if data is None:
        data = {}
    return PresenceConfig(**data)
