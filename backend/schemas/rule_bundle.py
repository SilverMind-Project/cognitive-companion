"""Portable rule bundle schemas -- import/export wire format.

All cross-references use stable string identifiers (labels, type_names,
sensor ids, person slugs) -- never database primary keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# -- Export metadata ----------------------------------------------------------


class ExportMetadata(BaseModel):
    schema_version: int = 1
    exported_at: datetime
    exported_by: str | None = None
    source: SourceInfo


class SourceInfo(BaseModel):
    app: str = "cognitive-companion"
    app_version: str


# -- References ---------------------------------------------------------------


class ReferenceBlock(BaseModel):
    sensors: list[str] = []
    persons: list[str] = []
    channels: list[str] = []
    llm_models: list[str] = []


# -- Steps --------------------------------------------------------------------


class StepBundle(BaseModel):
    label: str
    step_type: str
    schema_version: int = 1
    enabled: bool = True
    position_x: float = 0.0
    position_y: float = 0.0
    config: dict[str, Any] = {}


# -- Contexts -----------------------------------------------------------------


class ContextBundle(BaseModel):
    context_type: str
    schema_version: int = 1
    config: dict[str, Any] = {}
    negate: bool = False


# -- Dependencies -------------------------------------------------------------


class DependencyBundle(BaseModel):
    parent_rule_name: str  # resolved by name on import
    lookback_minutes: int = 30
    require_success: bool = True


# -- Edges --------------------------------------------------------------------


class EdgeBundle(BaseModel):
    """Portable representation of a pipeline edge."""

    source_label: str
    source_port: str
    target_label: str
    target_port: str = "main"


# -- Rule ---------------------------------------------------------------------


class RuleDefinition(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    trigger_types: list[str] = ["sensor_event"]
    primary_sensor_ref: SensorRef | None = None
    cool_off_minutes: int = 5
    max_daily_triggers: int = 3
    max_concurrent_executions: int = 1
    execution_timeout_minutes: int = 5
    webhook_config: dict[str, Any] | None = None
    occupancy_config: dict[str, Any] | None = None
    telegram_trigger_config: dict[str, Any] | None = None
    schedule_timezone: str | None = None  # captured from the source install
    cron_expressions: list[CronExpressionRef] = []


class SensorRef(BaseModel):
    kind: Literal["sensor"] = "sensor"
    label: str  # sensor_id, e.g. "bathroom_cam"


class CronExpressionRef(BaseModel):
    expression: str
    timezone: str = "UTC"


# -- Top-level bundle ---------------------------------------------------------


class RuleBundle(BaseModel):
    """A self-contained, install-portable rule document."""

    schema_version: int = 1
    exported_at: datetime | None = None
    exported_by: str | None = None
    source: SourceInfo | None = None
    rule: RuleDefinition
    references: ReferenceBlock = ReferenceBlock()
    contexts: list[ContextBundle] = []
    steps: list[StepBundle] = []
    edges: list[EdgeBundle] = []
    dependencies: list[DependencyBundle] = []


# -- Import result ------------------------------------------------------------


class StepImportResult(BaseModel):
    label: str
    step_type: str
    status: Literal["ok", "migrated", "warning", "error"]
    description: str = ""


class ImportReport(BaseModel):
    """Returned by preview and commit endpoints."""

    status: Literal["ok", "warning", "error"]
    rule_name: str | None = None
    rule_id: int | None = None  # set on successful commit
    steps: list[StepImportResult] = []
    warnings: list[str] = []
    errors: list[str] = []
    min_app_version_required: str | None = None
