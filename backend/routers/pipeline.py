"""Pipeline metadata endpoints.

Serves step type metadata, channel metadata, filter metadata, and
LLM model registry metadata to the frontend for dynamic form generation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.channels import ChannelRegistry
from backend.core.auth import AuthContext, require_permission
from backend.filters import FilterRegistry
from backend.steps import StepRegistry

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


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
