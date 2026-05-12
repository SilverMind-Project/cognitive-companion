"""Pipeline metadata endpoints.

Serves step type metadata, channel metadata, filter metadata, and
LLM model registry metadata to the frontend for dynamic form generation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.channels import ChannelRegistry
from backend.core.auth import AuthContext, require_permission
from backend.filters import FilterRegistry
from backend.schemas.pipeline_types import (
    ChannelTypeOut,
    CronPreviewRequest,
    CronPreviewResponse,
    FilterTypeOut,
    LLMModelOut,
    StepTypeOut,
)
from backend.steps import StepRegistry

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/step-types", response_model=list[StepTypeOut])
def list_step_types(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return metadata for all registered pipeline step types."""
    return [
        StepTypeOut(
            type_name=m.type_name,
            display_name=m.display_name,
            category=m.category,
            icon=m.icon,
            description=m.description,
            config_schema=m.config_schema,
            default_config=m.default_config,
            deprecated=m.deprecated,
        )
        for m in StepRegistry.all_metadata()
    ]


@router.get("/channel-types", response_model=list[ChannelTypeOut])
def list_channel_types(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return metadata for all registered notification channels."""
    return [
        ChannelTypeOut(
            channel_name=m.channel_name,
            display_name=m.display_name,
            description=m.description,
            config_schema=m.config_schema,
        )
        for m in ChannelRegistry.all_metadata()
    ]


@router.get("/filter-types", response_model=list[FilterTypeOut])
def list_filter_types(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return metadata for all registered context filter types."""
    return [
        FilterTypeOut(
            filter_type=m.filter_type,
            display_name=m.display_name,
            description=m.description,
            config_schema=m.config_schema,
        )
        for m in FilterRegistry.all_metadata()
    ]


@router.get("/llm-models", response_model=list[LLMModelOut])
def list_llm_models(
    request: Request,
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return all named LLM models from the registry (for the llm_call step UI)."""
    registry = getattr(request.app.state, "llm_model_registry", None)
    if registry is None:
        return []
    return [
        LLMModelOut(
            id=cfg.id,
            name=cfg.name,
            api_type=cfg.api_type,
            capabilities=cfg.capabilities,
            guided_decoding=cfg.guided_decoding,
            supports_thinking=cfg.supports_thinking,
            default_temperature=cfg.temperature,
            default_top_p=cfg.top_p,
            default_max_tokens=cfg.max_tokens,
        )
        for cfg in registry.all_configs()
    ]


# -- Cron preview ------------------------------------------------------------


@router.post("/cron/preview", response_model=CronPreviewResponse)
def preview_cron(
    payload: CronPreviewRequest,
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Validate a cron expression and return next N run times."""
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger as _CronTrigger

    try:
        trigger = _CronTrigger.from_crontab(payload.expression)
    except (ValueError, TypeError) as e:
        return CronPreviewResponse(
            valid=False,
            error=str(e),
            next_runs=[],
        )

    # Compute next N runs
    tz = ZoneInfo(payload.timezone) if payload.timezone else None
    now = datetime.now(tz or UTC)
    next_runs: list[str] = []
    current = now
    for _ in range(payload.count):
        next_fire = trigger.get_next_fire_time(current, now)
        if next_fire is None:
            break
        next_runs.append(next_fire.isoformat())
        current = next_fire

    # Parse expression into structured parts
    parts = payload.expression.strip().split()
    parsed = {"minute": [], "hour": [], "day_of_month": [], "month": [], "day_of_week": []}
    field_names = ["minute", "hour", "day_of_month", "month", "day_of_week"]
    for i, part in enumerate(parts):
        if i < len(field_names):
            parsed[field_names[i]] = _parse_cron_field(part)

    # Determine preset
    preset = _detect_cron_preset(parsed)

    return CronPreviewResponse(
        valid=True,
        next_runs=next_runs,
        parsed=parsed,
        preset=preset,
        description=str(trigger),
    )


def _parse_cron_field(field: str) -> list:
    """Parse a single cron field into a list representation."""
    field = field.strip()
    if field == "*":
        return ["*"]
    parts = field.split(",")
    result = []
    for p in parts:
        if "/" in p:
            result.append(p)  # e.g. "*/5"
        elif "-" in p:
            result.append(p)  # e.g. "1-5"
        else:
            try:
                result.append(int(p))
            except ValueError:
                result.append(p)
    return result


def _detect_cron_preset(parsed: dict) -> str | None:
    """Attempt to detect which preset mode the cron expression fits."""
    minute = parsed.get("minute", [])
    hour = parsed.get("hour", [])
    dom = parsed.get("day_of_month", [])
    dow = parsed.get("day_of_week", [])

    if dom != ["*"]:
        return None

    # Daily / Weekly: specific hour and minute
    if len(hour) == 1 and isinstance(hour[0], int) and minute and isinstance(minute[0], int):
        return "weekly" if dow != ["*"] else "daily"

    # Hourly / Interval: every hour
    if hour == ["*"] and minute:
        if isinstance(minute[0], int) and len(minute) == 1:
            return "hourly"
        if len(minute) == 1 and isinstance(minute[0], str) and "/" in str(minute[0]):
            return "interval"

    return None
