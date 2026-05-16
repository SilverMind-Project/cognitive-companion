from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, field_validator

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime

_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# -- Pipeline Step -----------------------------------------------------------


class PipelineStepCreate(BaseModel):
    step_type: str
    label: str | None = None
    config_json: dict[str, Any] = {}
    enabled: bool = True
    next_step_on_true: int | None = None
    next_step_on_false: int | None = None

    @field_validator("label")
    @classmethod
    def label_must_be_slug(cls, v: str | None) -> str | None:
        if v is not None and not _LABEL_RE.match(v):
            raise ValueError("label must match ^[a-z][a-z0-9_]*$")
        return v


class PipelineStepUpdate(BaseModel):
    step_type: str | None = None
    label: str | None = None
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None
    next_step_on_true: int | None = None
    next_step_on_false: int | None = None

    @field_validator("label")
    @classmethod
    def label_must_be_slug(cls, v: str | None) -> str | None:
        if v is not None and not _LABEL_RE.match(v):
            raise ValueError("label must match ^[a-z][a-z0-9_]*$")
        return v


class PipelineStepOut(OutSchema):
    id: int
    rule_id: int
    order: int
    step_type: str
    label: str | None
    config_json: dict[str, Any]
    enabled: bool
    next_step_on_true: int | None
    next_step_on_false: int | None



class PipelineStepReorder(BaseModel):
    """Ordered list of step IDs; position in the list becomes the new order value."""

    steps: list[int]


# -- Rule --------------------------------------------------------------------


class RuleCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    trigger_types: list[str] = ["sensor_event"]
    cron_trigger_ids: list[int] = []
    primary_sensor_id: str | None = None
    cool_off_minutes: int = 5
    max_daily_triggers: int = 3
    max_concurrent_executions: int = 1
    execution_timeout_minutes: int = 5
    webhook_config: dict[str, Any] | None = None
    occupancy_config: dict[str, Any] | None = None
    telegram_trigger_config: dict[str, Any] | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    trigger_types: list[str] | None = None
    cron_trigger_ids: list[int] | None = None
    primary_sensor_id: str | None = None
    cool_off_minutes: int | None = None
    max_daily_triggers: int | None = None
    max_concurrent_executions: int | None = None
    execution_timeout_minutes: int | None = None
    webhook_config: dict[str, Any] | None = None
    occupancy_config: dict[str, Any] | None = None
    telegram_trigger_config: dict[str, Any] | None = None


class RuleContextOut(OutSchema):
    id: int
    rule_id: int
    context_type: str
    config_json: dict[str, Any]
    negate: bool = False



class RuleDependencyOut(OutSchema):
    id: int
    dependent_rule_id: int
    parent_rule_id: int
    lookback_minutes: int
    require_success: bool



class CronTriggerOut(OutSchema):
    id: int
    name: str
    expression: str
    timezone: str
    enabled: bool


class RuleOut(OutSchema):
    id: int
    name: str
    description: str | None
    enabled: bool
    trigger_types: list[str]
    primary_sensor_id: str | None
    cool_off_minutes: int
    max_daily_triggers: int
    max_concurrent_executions: int
    execution_timeout_minutes: int
    webhook_config: dict[str, Any] | None = None
    occupancy_config: dict[str, Any] | None = None
    telegram_trigger_config: dict[str, Any] | None = None
    created_at: UTCDatetime
    updated_at: OptionalUTCDatetime
    steps: list[PipelineStepOut] = []
    contexts: list[RuleContextOut] = []
    dependencies: list[RuleDependencyOut] = []
    cron_triggers: list[CronTriggerOut] = []



class RuleExecutionCounts(BaseModel):
    last_15m: int = 0
    last_1h: int = 0
    last_24h: int = 0
    last_30d: int = 0


class RuleListOut(OutSchema):
    """Lighter version without sub-resources for list endpoints."""

    id: int
    name: str
    description: str | None
    enabled: bool
    trigger_types: list[str]
    cool_off_minutes: int
    max_daily_triggers: int
    max_concurrent_executions: int
    execution_timeout_minutes: int
    created_at: UTCDatetime
    execution_counts: RuleExecutionCounts = RuleExecutionCounts()



# -- Context -----------------------------------------------------------------


class ContextCreate(BaseModel):
    context_type: str
    config_json: dict[str, Any] = {}
    negate: bool = False


# -- Dependency --------------------------------------------------------------


class DependencyCreate(BaseModel):
    parent_rule_id: int
    lookback_minutes: int = 30
    require_success: bool = True


# -- Cron Triggers -----------------------------------------------------------


class CronTriggerCreate(BaseModel):
    name: str
    expression: str
    timezone: str = "UTC"
    enabled: bool = True

    @field_validator("expression")
    @classmethod
    def expression_must_be_valid_cron(cls, v: str) -> str:
        from apscheduler.triggers.cron import CronTrigger

        try:
            CronTrigger.from_crontab(v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid cron expression: {e}") from e
        return v


class CronTriggerUpdate(BaseModel):
    name: str | None = None
    expression: str | None = None
    timezone: str | None = None
    enabled: bool | None = None

    @field_validator("expression")
    @classmethod
    def expression_must_be_valid_cron(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from apscheduler.triggers.cron import CronTrigger

        try:
            CronTrigger.from_crontab(v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid cron expression: {e}") from e
        return v
