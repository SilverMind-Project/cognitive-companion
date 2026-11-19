"""Wearables BFF router: devices, consented bindings, RF nodes, and site-config."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response

from backend.core.auth import AuthContext, actor_from_auth, require_token
from backend.routers.dependencies import (
    get_rf_node_service,
    get_wearable_binding_service,
    get_wearable_device_service,
    get_wearable_site_config_service,
)
from backend.schemas.wearables import (
    RfNodeCreate,
    RfNodeListOut,
    RfNodeOut,
    RfNodeSurveyCheckOut,
    RfNodeSurveyCheckRequest,
    RfNodeUpdate,
    WearableAssignmentsOut,
    WearableBindingCreate,
    WearableBindingOut,
    WearableDeviceCreate,
    WearableDeviceListOut,
    WearableDeviceOut,
    WearableDeviceStatusOut,
    WearableDeviceUpdate,
    WearableSiteConfigOut,
    WearableUnbindRequest,
)
from backend.services.wearables import (
    RfNodeService,
    WearableBindingService,
    WearableDeviceService,
    WearableSiteConfigService,
)

router = APIRouter(prefix="/wearables", tags=["wearables"])


@router.get("/site-config", response_model=WearableSiteConfigOut)
async def get_wearable_site_config(
    svc: WearableSiteConfigService = Depends(get_wearable_site_config_service),
    _auth: AuthContext = Depends(require_token("wearables:site_config")),
) -> WearableSiteConfigOut:
    """Serve RF nodes in metres, time-bounded bindings, and devices for CTS and rf-ingress."""
    return svc.build_site_config()


@router.get("/assignments", response_model=WearableAssignmentsOut)
async def list_wearable_assignments(
    svc: WearableBindingService = Depends(get_wearable_binding_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> WearableAssignmentsOut:
    """Return active wearable devices grouped per household member, plus unbound devices."""
    return svc.list_member_assignments()


@router.get("/devices", response_model=WearableDeviceListOut)
async def list_wearable_devices(
    active_only: bool = Query(default=False),
    svc: WearableDeviceService = Depends(get_wearable_device_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> WearableDeviceListOut:
    """List registered wearable devices."""
    return svc.list_devices(active_only=active_only)


@router.post("/devices", response_model=WearableDeviceOut, status_code=201)
async def create_wearable_device(
    body: WearableDeviceCreate,
    svc: WearableDeviceService = Depends(get_wearable_device_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> WearableDeviceOut:
    """Register a new wearable device."""
    return svc.create_device(body, actor=actor_from_auth(auth))


@router.get("/devices/{device_id}", response_model=WearableDeviceOut)
async def get_wearable_device(
    device_id: uuid.UUID,
    svc: WearableDeviceService = Depends(get_wearable_device_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> WearableDeviceOut:
    """Fetch a single registered wearable device."""
    return svc.get_device(device_id)


@router.patch("/devices/{device_id}", response_model=WearableDeviceOut)
async def update_wearable_device(
    device_id: uuid.UUID,
    body: WearableDeviceUpdate,
    svc: WearableDeviceService = Depends(get_wearable_device_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> WearableDeviceOut:
    """Update a wearable device label, hardware key, or active status."""
    return svc.update_device(device_id, body, actor=actor_from_auth(auth))


@router.get("/devices/{device_id}/status", response_model=WearableDeviceStatusOut)
async def get_wearable_device_status(
    device_id: uuid.UUID,
    svc: WearableDeviceService = Depends(get_wearable_device_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> WearableDeviceStatusOut:
    """Report active wearer, last-heard freshness, and battery status for one device."""
    return svc.get_device_status(device_id)


@router.get("/devices/{device_id}/bindings", response_model=list[WearableBindingOut])
async def list_wearable_device_bindings(
    device_id: uuid.UUID,
    svc: WearableBindingService = Depends(get_wearable_binding_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> list[WearableBindingOut]:
    """List full binding history for one wearable device, newest first."""
    return svc.list_history(device_id)


@router.post("/devices/{device_id}/bind", response_model=WearableBindingOut, status_code=201)
async def bind_wearable_device(
    device_id: uuid.UUID,
    body: WearableBindingCreate,
    svc: WearableBindingService = Depends(get_wearable_binding_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> WearableBindingOut:
    """Bind a wearable device to a household member after recording consent."""
    return svc.bind(
        device_id,
        body.member_id,
        consent_recorded_by=body.consent_recorded_by,
        created_by=actor_from_auth(auth),
        at=body.valid_from,
    )


@router.post("/devices/{device_id}/unbind", response_model=WearableBindingOut)
async def unbind_wearable_device(
    device_id: uuid.UUID,
    body: WearableUnbindRequest | None = None,
    svc: WearableBindingService = Depends(get_wearable_binding_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> WearableBindingOut:
    """Close the active binding on a wearable device."""
    return svc.unbind(
        device_id,
        actor=actor_from_auth(auth),
        at=body.at if body is not None else None,
    )


@router.get("/nodes", response_model=RfNodeListOut)
async def list_rf_nodes(
    active_only: bool = Query(default=False),
    svc: RfNodeService = Depends(get_rf_node_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> RfNodeListOut:
    """List registered fixed RF nodes with floor-plan readiness and metre projections."""
    return svc.list_nodes(active_only=active_only)


@router.post("/nodes/survey-check", response_model=RfNodeSurveyCheckOut)
async def check_rf_node_survey(
    body: RfNodeSurveyCheckRequest,
    svc: RfNodeService = Depends(get_rf_node_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> RfNodeSurveyCheckOut:
    """Compare clicked floor-plan coordinates against tape-measured distances."""
    return svc.survey_check(body)


@router.post("/nodes", response_model=RfNodeOut, status_code=201)
async def create_rf_node(
    body: RfNodeCreate,
    svc: RfNodeService = Depends(get_rf_node_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> RfNodeOut:
    """Place a new fixed RF node on the household floor plan."""
    return svc.create_node(body, actor=actor_from_auth(auth))


@router.get("/nodes/{node_id}", response_model=RfNodeOut)
async def get_rf_node(
    node_id: uuid.UUID,
    svc: RfNodeService = Depends(get_rf_node_service),
    _auth: AuthContext = Depends(require_token("wearables:read")),
) -> RfNodeOut:
    """Fetch a single fixed RF node."""
    return svc.get_node(node_id)


@router.patch("/nodes/{node_id}", response_model=RfNodeOut)
async def update_rf_node(
    node_id: uuid.UUID,
    body: RfNodeUpdate,
    svc: RfNodeService = Depends(get_rf_node_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> RfNodeOut:
    """Update a fixed RF node's position, mount height, role, or UWB parameters."""
    return svc.update_node(node_id, body, actor=actor_from_auth(auth))


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_rf_node(
    node_id: uuid.UUID,
    svc: RfNodeService = Depends(get_rf_node_service),
    auth: AuthContext = Depends(require_token("wearables:manage")),
) -> Response:
    """Delete a fixed RF node."""
    svc.delete_node(node_id, actor=actor_from_auth(auth))
    return Response(status_code=204)
