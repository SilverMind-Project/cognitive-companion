"""Pydantic wire models for pipeline metadata endpoints (step/channel/filter types)."""

from __future__ import annotations

from pydantic import BaseModel


class StepTypeOut(BaseModel):
    type_name: str
    display_name: str
    category: str
    icon: str
    description: str
    config_schema: dict
    default_config: dict
    deprecated: bool = False
    schema_version: int = 1
    ui_hints: dict | None = None
    output_schema: dict | None = None
    tags: list[str] = []
    output_ports: list[str] = ["main"]


class PipelineEdgeCreate(BaseModel):
    model_config = {"extra": "forbid"}

    source_step_id: int
    source_port: str = "main"
    target_step_id: int
    target_port: str = "main"


class PipelineEdgeOut(BaseModel):
    id: int
    rule_id: int
    source_step_id: int
    source_port: str
    target_step_id: int
    target_port: str

    model_config = {"from_attributes": True}


class PipelineEdgeBulkUpdate(BaseModel):
    """Replace all edges for a rule in one atomic operation."""

    model_config = {"extra": "forbid"}

    edges: list[PipelineEdgeCreate]


class ChannelTypeOut(BaseModel):
    channel_name: str
    display_name: str
    description: str
    config_schema: dict
    schema_version: int = 1


class FilterTypeOut(BaseModel):
    filter_type: str
    display_name: str
    description: str
    config_schema: dict
    schema_version: int = 1


class LLMModelOut(BaseModel):
    id: str
    name: str
    api_type: str
    capabilities: list[str]
    guided_decoding: bool
    supports_thinking: bool
    default_temperature: float | None
    default_top_p: float | None
    default_max_tokens: int


# -- Data keys (variable reference for autocomplete) -------------------------


class VariableEntry(BaseModel):
    key: str
    description: str
    type: str = "any"


class DataKeysResponse(BaseModel):
    trigger: list[VariableEntry]
    system: list[VariableEntry]
    step_outputs: dict[str, dict]  # step_type -> output_schema


# -- Cron preview ------------------------------------------------------------


class CronPreviewRequest(BaseModel):
    expression: str
    timezone: str | None = None
    count: int = 5


class CronPreviewResponse(BaseModel):
    valid: bool
    error: str | None = None
    next_runs: list[str]  # ISO 8601
    parsed: dict | None = None  # minute, hour, dom, month, dow
    preset: str | None = None
    description: str | None = None
