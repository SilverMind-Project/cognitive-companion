"""CTS presence endpoints.

Provides fused presence snapshot queries and configuration management.
When ``cts.enabled=false`` every handler returns 404 with
code ``cts.disabled``.

Routes:
    GET  /api/v1/cts/presence/{person_id}          : presence snapshot
    GET  /api/v1/cts/presence-config               : active fuser config
    POST /api/v1/cts/presence-config/reload         : reload from disk
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from backend.core.auth import require_permission
from backend.core.logging import get_logger
from backend.routers.cts_deps import cts_enabled
from backend.services.presence import (
    PresenceService,
    PresenceSnapshot,
)
from backend.services.presence.config import load_presence_config

logger = get_logger(__name__)

router = APIRouter(prefix="/cts", tags=["cts-presence"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class _PresenceSourceOut(BaseModel):
    """Serialized presence source (subset of PresenceSource)."""

    name: str
    confidence: float


class PresenceSnapshotOut(BaseModel):
    """Public-facing presence snapshot shape.

    This model is the contract between the BFF and all frontend consumers
    (PresenceWidget, CTSPresenceView, CTSDashboardView).  Any change to
    its fields is a breaking API change.
    """

    person_id: str
    status: str
    room_id: str | None = None
    room_name: str | None = None
    confidence: float
    last_seen_at: str | None = None
    dwell_minutes: float | None = None
    sources: list[_PresenceSourceOut] = Field(default_factory=list)
    inferred_at: str
    notes: str | None = None


class _ProviderSummary(BaseModel):
    """One-line summary of a provider in the fusion chain."""

    name: str
    priority: int
    config_summary: str


class FusionConfigOut(BaseModel):
    rule: str
    confidence_floor: float


class PresenceConfigOut(BaseModel):
    """Sanitized view of the active presence fuser configuration."""

    providers: list[_ProviderSummary]
    fusion: FusionConfigOut
    loaded_at: str
    config_path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot_to_out(snapshot: PresenceSnapshot) -> PresenceSnapshotOut:
    """Serialize a PresenceSnapshot to the public response model."""
    return PresenceSnapshotOut(
        person_id=snapshot.person_id,
        status=snapshot.status,
        room_id=str(snapshot.room_id) if snapshot.room_id is not None else None,
        room_name=snapshot.room_name,
        confidence=snapshot.confidence,
        last_seen_at=snapshot.last_seen_at.isoformat() if snapshot.last_seen_at else None,
        dwell_minutes=snapshot.dwell_minutes,
        sources=[
            _PresenceSourceOut(name=s.name, confidence=s.confidence) for s in snapshot.sources
        ],
        inferred_at=snapshot.inferred_at.isoformat(),
        notes=snapshot.notes,
    )


def _build_provider_summaries(
    presence_service: PresenceService,
) -> list[_ProviderSummary]:
    """Derive one-line summaries from the running provider list."""
    summaries: list[_ProviderSummary] = []
    for provider in presence_service.providers:
        name = provider.name
        priority = provider.priority
        # Build a human-readable summary from provider attributes.
        if name == "cts_location":
            summaries.append(
                _ProviderSummary(
                    name=name,
                    priority=priority,
                    config_summary=f"ttl {getattr(provider, '_ttl_seconds', 120)}s",
                )
            )
        elif name == "ha_bed_sensor":
            summaries.append(
                _ProviderSummary(
                    name=name,
                    priority=priority,
                    config_summary=f"{getattr(provider, '_entity_id', '?')} → {getattr(provider, '_room_name', '?')} ({getattr(provider, '_person_id', '?')})",
                )
            )
        elif name == "night_anchor":
            summaries.append(
                _ProviderSummary(
                    name=name,
                    priority=priority,
                    config_summary=f"anchor {getattr(provider, '_anchor_room_name', '?')}, lights {getattr(provider, '_light_entities', [])}",
                )
            )
        elif name == "stale_fallback":
            summaries.append(
                _ProviderSummary(
                    name=name,
                    priority=priority,
                    config_summary=f"ttl {getattr(provider, '_ttl_seconds', 3600)}s",
                )
            )
        elif name == "unknown_sentinel":
            summaries.append(
                _ProviderSummary(
                    name=name,
                    priority=priority,
                    config_summary="always returns UNKNOWN",
                )
            )
        else:
            summaries.append(
                _ProviderSummary(
                    name=name,
                    priority=priority,
                    config_summary="custom provider",
                )
            )
    return summaries


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# NOTE: /presence-config MUST be defined before /presence/{person_id} so that
# FastAPI does not match "presence-config" as a person_id value.


@router.get(
    "/presence-config",
    response_model=PresenceConfigOut,
    dependencies=[Depends(require_permission("cts.presence.view"))],
)
async def get_presence_config(request: Request) -> PresenceConfigOut:
    """Return the active presence fuser configuration (sanitized)."""
    cts_enabled()

    presence_service: PresenceService | None = request.app.state.presence
    if presence_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "presence.unavailable", "message": "PresenceService not initialized."},
        )

    providers = _build_provider_summaries(presence_service)
    return PresenceConfigOut(
        providers=providers,
        fusion=FusionConfigOut(
            rule=presence_service.fusion_rule,
            confidence_floor=presence_service.confidence_floor,
        ),
        loaded_at=datetime.now(UTC).isoformat(),
        config_path="config/presence.yaml",
    )


@router.post(
    "/presence-config/reload",
    response_model=PresenceConfigOut,
    dependencies=[Depends(require_permission("cts.presence.view"))],
)
async def reload_presence_config(request: Request) -> PresenceConfigOut:
    """Reload presence.yaml from disk into the running fuser.

    If validation fails, returns 422 with a parse-error detail and
    does NOT touch the running provider chain.
    """
    cts_enabled()

    presence_service: PresenceService | None = request.app.state.presence
    if presence_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "presence.unavailable", "message": "PresenceService not initialized."},
        )

    try:
        new_config = load_presence_config("config/presence.yaml")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "config.parse_error", "message": str(exc)},
        ) from exc

    try:
        from backend.integrations.ha_state_cache import HaStateCache
        from backend.services.presence.factory import build_providers

        ha_cache: HaStateCache | None = request.app.state.ha_state_cache
        if ha_cache is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "ha_cache.unavailable", "message": "HaStateCache not initialized."},
            )

        location_service = request.app.state.person_location_service
        if location_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "person_location_service.unavailable",
                    "message": "PersonLocationService not initialized.",
                },
            )

        # Build new provider chain.
        new_providers = build_providers(
            new_config,
            cache=ha_cache,
            location_service=location_service,
        )

        # Swap atomically.
        presence_service.reload(new_config, providers=new_providers)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "reload_error", "message": str(exc)},
        ) from exc

    providers = _build_provider_summaries(presence_service)
    return PresenceConfigOut(
        providers=providers,
        fusion=FusionConfigOut(
            rule=presence_service.fusion_rule,
            confidence_floor=presence_service.confidence_floor,
        ),
        loaded_at=datetime.now(UTC).isoformat(),
        config_path="config/presence.yaml",
    )


@router.get(
    "/presence/{person_id}",
    response_model=PresenceSnapshotOut,
    dependencies=[Depends(require_permission("cts.presence.view"))],
)
async def get_presence(
    person_id: str,
    request: Request,
    at: str | None = Query(
        None,
        description=(
            "ISO-8601 datetime for deterministic testing. Defaults to current time when absent."
        ),
    ),
) -> PresenceSnapshotOut:
    """Return the fused presence snapshot for *person_id*."""
    cts_enabled()

    presence_service: PresenceService | None = request.app.state.presence
    if presence_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "presence.unavailable", "message": "PresenceService not initialized."},
        )

    at_dt: datetime | None = None
    if at:
        at_dt = datetime.fromisoformat(at)

    snapshot = await presence_service.get(person_id, at=at_dt)
    return _snapshot_to_out(snapshot)
