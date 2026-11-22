"""Gateway client for the opt-in rf-ingress health endpoint.

All CC modules that need to reach rf-ingress MUST go through this class.
No other module may import ``httpx`` for upstream calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.integrations._upstream_base import UpstreamClient


@dataclass(frozen=True)
class RfIngressHealthInfo:
    """Validated live receiver and tag health summary returned by rf-ingress ``GET /health``."""

    status: str
    node_last_seen_age_s: dict[str, float]
    tag_last_seen_age_s: dict[str, float]
    tag_battery_fraction: dict[str, float]


class _RfIngressHealthPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    node_last_seen_age_s: dict[str, float] = Field(default_factory=dict)
    tag_last_seen_age_s: dict[str, float] = Field(default_factory=dict)
    tag_battery_fraction: dict[str, float] = Field(default_factory=dict)

    @field_validator("node_last_seen_age_s", "tag_last_seen_age_s")
    @classmethod
    def _validate_ages(cls, value: dict[str, float]) -> dict[str, float]:
        for key, age in value.items():
            if not math.isfinite(age) or age < 0.0:
                raise ValueError(f"Invalid age for {key!r}: {age!r}")
        return value

    @field_validator("tag_battery_fraction")
    @classmethod
    def _validate_batteries(cls, value: dict[str, float]) -> dict[str, float]:
        for key, frac in value.items():
            if not math.isfinite(frac) or not (0.0 <= frac <= 1.0):
                raise ValueError(f"Invalid battery fraction for {key!r}: {frac!r}")
        return value


class RfIngressClient(UpstreamClient):
    """BFF client for the optional rf-ingress service."""

    SERVICE_NAME = "rf_ingress"
    AUDIENCE = "rf-ingress"

    @property
    def configured(self) -> bool:
        """Return True when ``cts.upstream.rf_ingress.url`` is configured."""
        return bool(self._base)

    async def get_health(self) -> RfIngressHealthInfo:
        """Fetch and validate ``GET /health`` from rf-ingress."""
        r = await self._request("GET", "/health")
        parsed = _RfIngressHealthPayload.model_validate(r.json())
        return RfIngressHealthInfo(
            status=parsed.status,
            node_last_seen_age_s=dict(parsed.node_last_seen_age_s),
            tag_last_seen_age_s=dict(parsed.tag_last_seen_age_s),
            tag_battery_fraction=dict(parsed.tag_battery_fraction),
        )
