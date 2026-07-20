"""Admin endpoint response schemas (health probes, config, audits)."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from backend.schemas.common import OutSchema


class ServiceHealthOut(OutSchema):
    """Health probe result for one upstream service.

    ``extra="allow"`` is load-bearing, not laziness: the probes return
    ``{"configured": True, **upstream_health_body}``, and the admin dashboard reads
    service-specific keys straight off it -- TTS's ``default_engine``/``gpu_available``/
    ``gpu_name``, for example (`DashboardView.vue:239-240`). A strict model would silently drop
    every upstream key and the tiles would read "unknown - CPU". The two fields declared here are
    the ones this codebase guarantees; the rest are the upstream service's contract, not ours.

    ``status`` is absent when a healthy upstream body does not carry one.
    """

    model_config = ConfigDict(extra="allow")

    configured: bool
    status: str | None = None


class ServiceInfo(OutSchema):
    """Where to probe one upstream service, and whether it is configured at all."""

    enabled: bool
    health_url: str


class AppInfoOut(OutSchema):
    """Public application metadata, read during frontend bootstrap before a key is held."""

    name: str
    version: str
    timezone: str = Field(
        description="Operator-configured IANA zone; the UI formats all timestamps in it."
    )
    services: dict[str, ServiceInfo] = {}


class HealthOut(OutSchema):
    """Liveness probe."""

    status: str
    version: str


class ConfigReloadOut(OutSchema):
    status: str


class TelegramTriggerDefaultsOut(OutSchema):
    allowed_chat_ids: list[str] = []


class ChannelAuditIssue(OutSchema):
    """One pipeline step naming a channel the registry does not know."""

    step_id: int
    step_type: str
    rule_id: int
    unknown_channels: list[str] = []


class ChannelAuditOut(OutSchema):
    registered_channels: list[str] = []
    issues: list[ChannelAuditIssue] = []
    issue_count: int


# The config tree is free-form operator YAML (arbitrary nesting, sanitized), so there is no
# meaningful schema to declare beyond "a JSON object" -- generated clients get
# Record<string, unknown>, which is the honest type.
CurrentConfigOut = dict[str, Any]
