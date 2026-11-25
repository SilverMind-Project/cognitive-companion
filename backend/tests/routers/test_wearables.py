"""Router, auth (403), member-deletion cascade, and MCP parity tests for wearables."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.core.auth as auth_module
from backend.core.auth import KeyStore
from backend.core.config import settings
from backend.core.database import get_db
from backend.core.exceptions import register_exception_handlers
from backend.mcp.server import (
    _svc as mcp_svc,
)
from backend.mcp.server import (
    get_wearable_assignments as mcp_get_wearable_assignments,
)
from backend.mcp.server import (
    get_wearable_device_status as mcp_get_wearable_device_status,
)
from backend.models.household_settings import HouseholdSettings
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.wearable import WearableBinding
from backend.routers import persons, wearables
from backend.services.wearables import (
    PositionSensorService,
    RfNodeService,
    SqlAlchemyWearableRepository,
    WearableBindingService,
    WearableDeviceService,
    WearableSiteConfigService,
)

_ADMIN_KEY = "wear-admin-key"
_CAREGIVER_KEY = "wear-caregiver-key"
_INGRESS_KEY = "wear-ingress-key"
_READONLY_MCP_KEY = "wear-mcp-key"


@pytest.fixture
def wearable_client(db_factory, monkeypatch: pytest.MonkeyPatch):
    ks = KeyStore(
        api_keys=[
            {"key": _ADMIN_KEY, "name": "Admin Alice", "roles": ["admin"]},
            {"key": _CAREGIVER_KEY, "name": "Caregiver Bob", "roles": ["caregiver"]},
            {"key": _INGRESS_KEY, "name": "Ingress Service", "roles": ["cts_ingress"]},
            {"key": _READONLY_MCP_KEY, "name": "MCP Agent", "roles": ["mcp_readonly"]},
        ],
        roles=settings.get("auth.roles", {}),
    )
    monkeypatch.setattr(auth_module, "_default_keystore", ks)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(wearables.router, prefix="/api/v1")
    app.include_router(persons.router, prefix="/api/v1")
    repo = SqlAlchemyWearableRepository(db_factory)
    dev_svc = WearableDeviceService(repo)
    bind_svc = WearableBindingService(repo)
    node_svc = RfNodeService(repo)
    site_svc = WearableSiteConfigService(repo)

    app.state.wearable_device_service = dev_svc
    app.state.wearable_binding_service = bind_svc
    app.state.rf_node_service = node_svc
    app.state.position_sensor_service = PositionSensorService(repo)
    app.state.wearable_site_config_service = site_svc
    app.state.person_id_client = MagicMock(delete_member=AsyncMock(return_value=True))
    app.state.orchestrator_client = MagicMock(purge_gallery_identity=AsyncMock(return_value=True))

    def _override_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db

    orig_dev = mcp_svc.wearable_device_service
    orig_bind = mcp_svc.wearable_binding_service
    mcp_svc.wearable_device_service = dev_svc
    mcp_svc.wearable_binding_service = bind_svc

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        mcp_svc.wearable_device_service = orig_dev
        mcp_svc.wearable_binding_service = orig_bind


def _seed(db_factory) -> None:
    with db_factory() as db:
        db.add(
            HouseholdSettings(
                id=1,
                floor_plan_key="floor-plans/home.png",
                floor_plan_width=1000,
                floor_plan_height=500,
                floor_meters_per_pixel=0.01,
            )
        )
        db.add(HouseholdMember(id="amma", name="Amma"))
        db.commit()


def test_wearable_auth_403_and_role_boundaries(wearable_client: TestClient, db_factory) -> None:
    _seed(db_factory)
    dev_body = {
        "tag_id": "band-auth",
        "device_kind": "ble_beacon",
        "label": "Band",
        "adapter_id": "ble-home",
        "hardware_key": "uuid:1:9",
    }

    # Caregiver cannot create devices or read site-config.
    assert (
        wearable_client.post(
            "/api/v1/wearables/devices",
            json=dev_body,
            headers={"X-API-Key": _CAREGIVER_KEY},
        ).status_code
        == 403
    )
    assert (
        wearable_client.get(
            "/api/v1/wearables/site-config",
            headers={"X-API-Key": _CAREGIVER_KEY},
        ).status_code
        == 403
    )
    # MCP readonly key cannot mutate wearable devices or read site-config,
    # while sharing wearables:read with its MCP read-tool twins.
    assert (
        wearable_client.post(
            "/api/v1/wearables/devices",
            json=dev_body,
            headers={"X-API-Key": _READONLY_MCP_KEY},
        ).status_code
        == 403
    )
    assert (
        wearable_client.get(
            "/api/v1/wearables/site-config",
            headers={"X-API-Key": _READONLY_MCP_KEY},
        ).status_code
        == 403
    )
    assert (
        wearable_client.get(
            "/api/v1/wearables/devices",
            headers={"X-API-Key": _READONLY_MCP_KEY},
        ).status_code
        == 200
    )

    # Admin can create; caregiver can read; cts_ingress can read site-config.
    created = wearable_client.post(
        "/api/v1/wearables/devices",
        json=dev_body,
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert created.status_code == 201
    assert (
        wearable_client.get(
            "/api/v1/wearables/devices",
            headers={"X-API-Key": _CAREGIVER_KEY},
        ).status_code
        == 200
    )
    site_resp = wearable_client.get(
        "/api/v1/wearables/site-config",
        headers={"X-API-Key": _INGRESS_KEY},
    )
    assert site_resp.status_code == 200
    assert site_resp.json()["version"].startswith("sha256:")


@pytest.mark.asyncio
async def test_bind_consent_actor_mcp_parity_and_member_delete_cascade(
    wearable_client: TestClient, db_factory
) -> None:
    _seed(db_factory)
    created = wearable_client.post(
        "/api/v1/wearables/devices",
        json={
            "tag_id": "grandma-band",
            "device_kind": "ble_beacon",
            "label": "Grandma's wristband",
            "adapter_id": "ble-home",
            "hardware_key": "uuid:1:42",
        },
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert created.status_code == 201
    device_id = created.json()["id"]

    # Binding without consent_confirmed=true is rejected (422).
    no_consent = wearable_client.post(
        f"/api/v1/wearables/devices/{device_id}/bind",
        json={
            "member_id": "amma",
            "consent_confirmed": False,
            "consent_recorded_by": "Sriram",
        },
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert no_consent.status_code == 422

    bound = wearable_client.post(
        f"/api/v1/wearables/devices/{device_id}/bind",
        json={
            "member_id": "amma",
            "consent_confirmed": True,
            "consent_recorded_by": "Sriram",
        },
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert bound.status_code == 201
    # Actor comes from auth key name, never "system".
    assert bound.json()["created_by"] == "Admin Alice"

    # BFF <-> MCP parity: both call the same service methods and return matching envelopes.
    bff_assignments = wearable_client.get(
        "/api/v1/wearables/assignments",
        headers={"X-API-Key": _CAREGIVER_KEY},
    ).json()
    mcp_assignments = await mcp_get_wearable_assignments()
    assert bff_assignments["members"] == mcp_assignments["members"]
    assert len(mcp_assignments["members"]) == 1
    assert mcp_assignments["members"][0]["devices"][0]["tag_id"] == "grandma-band"

    bff_status = wearable_client.get(
        f"/api/v1/wearables/devices/{device_id}/status",
        headers={"X-API-Key": _CAREGIVER_KEY},
    ).json()
    mcp_status = await mcp_get_wearable_device_status("grandma-band")
    assert bff_status["tag_id"] == mcp_status["tag_id"] == "grandma-band"
    assert bff_status["bound_member_id"] == mcp_status["bound_member_id"] == "amma"
    assert bff_status["reporting"] is False
    assert mcp_status["reporting"] is False

    # Deleting the member closes active wearable bindings cleanly (no FK failure) and drops
    # the member from site-config bindings.
    deleted = wearable_client.delete(
        "/api/v1/persons/amma",
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert deleted.status_code == 204

    with db_factory() as db:
        rows = db.query(WearableBinding).all()
        assert len(rows) == 1
        assert rows[0].valid_to is not None
        assert rows[0].member_id is None
        assert rows[0].valid_to <= datetime.now(UTC)

    site_cfg = wearable_client.get(
        "/api/v1/wearables/site-config",
        headers={"X-API-Key": _INGRESS_KEY},
    ).json()
    assert site_cfg["bindings"] == []


def test_position_sensor_endpoints_permissions_and_site_config(
    wearable_client: TestClient, db_factory
) -> None:
    _seed(db_factory)
    with db_factory() as db:
        room = Room(name="Bathroom", floor_polygon=[[0.6, 0.0], [1.0, 0.0], [1.0, 1.0], [0.6, 1.0]])
        db.add(room)
        db.commit()
        db.refresh(room)
        room_id = room.id
    body = {
        "sensor_id": "radar-bathroom-1",
        "label": "Bathroom radar",
        "modality": "mmwave_radar",
        "room_id": room_id,
        "x_norm": 0.8,
        "y_norm": 0.5,
    }
    denied = wearable_client.post(
        "/api/v1/wearables/position-sensors",
        json=body,
        headers={"X-API-Key": _READONLY_MCP_KEY},
    )
    assert denied.status_code == 403

    created = wearable_client.post(
        "/api/v1/wearables/position-sensors", json=body, headers={"X-API-Key": _ADMIN_KEY}
    )
    assert created.status_code == 201, created.text
    sensor = created.json()
    assert sensor["x_m"] == pytest.approx(8.0)
    assert sensor["calibration_residual_m"] == pytest.approx(0.10)
    assert sensor["room_name"] == "Bathroom"

    duplicate = wearable_client.post(
        "/api/v1/wearables/position-sensors", json=body, headers={"X-API-Key": _ADMIN_KEY}
    )
    assert duplicate.status_code == 409

    listed = wearable_client.get(
        "/api/v1/wearables/position-sensors", headers={"X-API-Key": _CAREGIVER_KEY}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    site = wearable_client.get("/api/v1/wearables/site-config", headers={"X-API-Key": _INGRESS_KEY})
    assert site.status_code == 200
    assert [s["sensor_id"] for s in site.json()["position_sensors"]] == ["radar-bathroom-1"]

    patched = wearable_client.patch(
        f"/api/v1/wearables/position-sensors/{sensor['id']}",
        json={"yaw_deg": 90.0},
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert patched.status_code == 200
    assert patched.json()["yaw_deg"] == pytest.approx(90.0)

    null_patch = wearable_client.patch(
        f"/api/v1/wearables/position-sensors/{sensor['id']}",
        json={"x_norm": None},
        headers={"X-API-Key": _ADMIN_KEY},
    )
    assert null_patch.status_code == 422

    deleted = wearable_client.delete(
        f"/api/v1/wearables/position-sensors/{sensor['id']}", headers={"X-API-Key": _ADMIN_KEY}
    )
    assert deleted.status_code == 204
    missing = wearable_client.get(
        f"/api/v1/wearables/position-sensors/{sensor['id']}", headers={"X-API-Key": _ADMIN_KEY}
    )
    assert missing.status_code == 404
