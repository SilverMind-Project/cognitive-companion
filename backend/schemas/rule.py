from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.schemas.common import OptionalUTCDatetime, UTCDatetime

# -- Pipeline Step -----------------------------------------------------------


class PipelineStepCreate(BaseModel):
    step_type: str
    label: str | None = None
    config_json: dict[str, Any] = {}
    enabled: bool = True
    next_step_on_true: int | None = None
    next_step_on_false: int | None = None


class PipelineStepUpdate(BaseModel):
    step_type: str | None = None
    label: str | None = None
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None
    next_step_on_true: int | None = None
    next_step_on_false: int | None = None


class PipelineStepOut(BaseModel):
    id: int
    rule_id: int
    order: int
    step_type: str
    label: str | None
    config_json: dict[str, Any]
    enabled: bool
    next_step_on_true: int | None
    next_step_on_false: int | None

    model_config = {"from_attributes": True}


class PipelineStepReorder(BaseModel):
    """Ordered list of step IDs; position in the list becomes the new order value."""

    steps: list[int]


# -- Rule --------------------------------------------------------------------


class RuleCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    trigger_type: str = "sensor_event"
    schedule_cron: str | None = None
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
    trigger_type: str | None = None
    schedule_cron: str | None = None
    primary_sensor_id: str | None = None
    cool_off_minutes: int | None = None
    max_daily_triggers: int | None = None
    max_concurrent_executions: int | None = None
    execution_timeout_minutes: int | None = None
    webhook_config: dict[str, Any] | None = None
    occupancy_config: dict[str, Any] | None = None
    telegram_trigger_config: dict[str, Any] | None = None


class RuleContextOut(BaseModel):
    id: int
    rule_id: int
    context_type: str
    config_json: dict[str, Any]
    negate: bool = False

    model_config = {"from_attributes": True}


class RuleDependencyOut(BaseModel):
    id: int
    dependent_rule_id: int
    parent_rule_id: int
    lookback_minutes: int
    require_success: bool

    model_config = {"from_attributes": True}


class RuleOut(BaseModel):
    id: int
    name: str
    description: str | None
    enabled: bool
    trigger_type: str
    schedule_cron: str | None
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

    model_config = {"from_attributes": True}


class RuleListOut(BaseModel):
    """Lighter version without sub-resources for list endpoints."""

    id: int
    name: str
    description: str | None
    enabled: bool
    trigger_type: str
    schedule_cron: str | None
    cool_off_minutes: int
    max_daily_triggers: int
    max_concurrent_executions: int
    execution_timeout_minutes: int
    created_at: UTCDatetime

    model_config = {"from_attributes": True}


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
