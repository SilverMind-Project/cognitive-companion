"""Pipeline metadata endpoints.

Serves step type metadata, channel metadata, filter metadata,
LLM model registry metadata, and data-keys variable reference
to the frontend for dynamic form generation and autocomplete.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.channels import ChannelRegistry
from backend.core.auth import AuthContext, require_permission
from backend.filters import FilterRegistry
from backend.integrations.llm import LLMModelRegistry
from backend.schemas.pipeline_types import (
    ChannelTypeOut,
    CronPreviewRequest,
    CronPreviewResponse,
    DataKeysResponse,
    FilterTypeOut,
    LLMModelOut,
    StepTypeOut,
    VariableEntry,
)
from backend.steps import StepRegistry

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/step-types", response_model=list[StepTypeOut])
def list_step_types(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return metadata for all registered pipeline step types."""
    StepRegistry.discover()
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
            schema_version=m.schema_version,
            ui_hints=m.ui_hints if m.ui_hints else None,
            output_schema=m.output_schema if m.output_schema else None,
            tags=list(m.tags),
        )
        for m in StepRegistry.all_metadata()
    ]


@router.get("/channel-types", response_model=list[ChannelTypeOut])
def list_channel_types(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return metadata for all registered notification channels."""
    ChannelRegistry.discover()
    return [
        ChannelTypeOut(
            channel_name=m.channel_name,
            display_name=m.display_name,
            description=m.description,
            config_schema=m.config_schema,
            schema_version=m.schema_version,
        )
        for m in ChannelRegistry.all_metadata()
    ]


@router.get("/filter-types", response_model=list[FilterTypeOut])
def list_filter_types(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return metadata for all registered context filter types."""
    FilterRegistry.discover()
    return [
        FilterTypeOut(
            filter_type=m.filter_type,
            display_name=m.display_name,
            description=m.description,
            config_schema=m.config_schema,
            schema_version=m.schema_version,
        )
        for m in FilterRegistry.all_metadata()
    ]


@router.get("/llm-models", response_model=list[LLMModelOut])
def list_llm_models(
    request: Request,
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return all named LLM models from the registry (for the llm_call step UI)."""
    registry: LLMModelRegistry | None = request.app.state.llm_model_registry
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


# -- Data keys (variable reference for autocomplete) -------------------------


# Static trigger/system variables exposed to template autocomplete.
_TRIGGER_VARS: list[VariableEntry] = [
    VariableEntry(key="trigger.sensor_id", description="Sensor that triggered the pipeline", type="string"),
    VariableEntry(key="trigger.room_name", description="Room where the trigger originated", type="string"),
    VariableEntry(key="trigger.media_paths", description="Media files captured at trigger time", type="list"),
    VariableEntry(key="trigger.type", description="Trigger type (sensor_event, cron, manual, etc.)", type="string"),
    VariableEntry(key="trigger_input", description="Raw webhook/telegram payload (if applicable)", type="any"),
    VariableEntry(key="trigger_input.command", description="Telegram command text", type="string"),
    VariableEntry(key="trigger_input.chat_id", description="Telegram chat ID", type="string"),
    VariableEntry(key="trigger_input.args", description="Telegram command arguments", type="list"),
    VariableEntry(key="trigger_input.text", description="Telegram message text", type="string"),
]

_SYSTEM_VARS: list[VariableEntry] = [
    VariableEntry(key="system.local_time", description="Current local time (e.g. 02:30 PM)", type="string"),
    VariableEntry(key="system.local_date", description="Current local date (e.g. 2026-05-12)", type="string"),
    VariableEntry(key="system.local_day_of_week", description="Current day of week (e.g. Monday)", type="string"),
    VariableEntry(key="system.timezone", description="Operator timezone (e.g. America/Los_Angeles)", type="string"),
]


@router.get("/data-keys", response_model=DataKeysResponse)
def get_data_keys(
    _auth: AuthContext = Depends(require_permission("rules:read")),
):
    """Return the complete variable reference for template autocomplete.

    Includes trigger/system variables plus per-step-type output schemas
    keyed by step type_name so the frontend can build ``steps.<label>.outputs.*``
    suggestions from the current pipeline's labels.
    """
    StepRegistry.discover()
    step_outputs: dict[str, dict] = {}
    for m in StepRegistry.all_metadata():
        if m.output_schema:
            step_outputs[m.type_name] = m.output_schema

    return DataKeysResponse(
        trigger=_TRIGGER_VARS,
        system=_SYSTEM_VARS,
        step_outputs=step_outputs,
    )


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
