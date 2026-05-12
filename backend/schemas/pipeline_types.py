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


class ChannelTypeOut(BaseModel):
    channel_name: str
    display_name: str
    description: str
    config_schema: dict


class FilterTypeOut(BaseModel):
    filter_type: str
    display_name: str
    description: str
    config_schema: dict


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
