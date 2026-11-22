"""Service tests for wearable devices, consented bindings, RF nodes, and site-config."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cts_contracts import DeviceKind, RangingTechnology, RfNodeRole

from backend.core.exceptions import ConflictError, ValidationError
from backend.integrations.rf_ingress_client import RfIngressHealthInfo
from backend.models.household_settings import HouseholdSettings
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.schemas.wearables import (
    RfNodeCreate,
    RfNodeSurveyCheckRequest,
    RfNodeUpdate,
    SurveyDistanceMeasurement,
    WearableDeviceCreate,
    WearableDeviceUpdate,
)
from backend.services.identity_readiness_rules import WearablesHealth, wearables_step
from backend.services.wearables import (
    RfNodeService,
    SqlAlchemyWearableRepository,
    WearableBindingService,
    WearableDeviceService,
    WearableSiteConfigService,
)


def _seed_floor_plan_and_members(db_factory) -> int:
    with db_factory() as db:
        db.add(
            HouseholdSettings(
                id=1,
                floor_plan_key="floor-plans/test.png",
                floor_plan_width=1000,
                floor_plan_height=800,
                floor_meters_per_pixel=0.01,  # 10.0 m x 8.0 m
            )
        )
        room = Room(
            name="Living Room",
            floor_polygon=[[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]],
        )
        db.add(room)
        db.add_all(
            [
                HouseholdMember(id="amma", name="Amma"),
                HouseholdMember(id="sriram", name="Sriram"),
            ]
        )
        db.commit()
        db.refresh(room)
        return room.id


def test_multiple_devices_per_member_and_dual_mode_watch_bindings(db_factory) -> None:
    _seed_floor_plan_and_members(db_factory)
    t0 = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)
    repo = SqlAlchemyWearableRepository(db_factory)
    dev_svc = WearableDeviceService(repo, clock=lambda: t0)
    bind_svc = WearableBindingService(repo, clock=lambda: t0)
    site_svc = WearableSiteConfigService(repo, clock=lambda: t0)

    ble_watch = dev_svc.create_device(
        WearableDeviceCreate(
            tag_id="pw5-ble",
            device_kind=DeviceKind.WATCH,
            label="Pixel Watch 5 (BLE)",
            adapter_id="ble-home",
            hardware_key="e2c56db5:1:101",
        ),
        actor="Admin",
    )
    uwb_watch = dev_svc.create_device(
        WearableDeviceCreate(
            tag_id="pw5-uwb",
            device_kind=DeviceKind.WATCH,
            label="Pixel Watch 5 (UWB)",
            adapter_id="uwb-watch",
            hardware_key="watch-uwb-01",
        ),
        actor="Admin",
    )

    # One member can hold both BLE and UWB bindings at the same time (dual-mode watch).
    bind_svc.bind(
        ble_watch.id,
        "sriram",
        consent_recorded_by="Sriram",
        created_by="Admin",
        at=t0,
    )
    bind_svc.bind(
        uwb_watch.id,
        "sriram",
        consent_recorded_by="Sriram",
        created_by="Admin",
        at=t0,
    )

    # One device cannot be bound to a second member while an active binding exists.
    with pytest.raises(ConflictError):
        bind_svc.bind(
            ble_watch.id,
            "amma",
            consent_recorded_by="Admin",
            created_by="Admin",
            at=t0 + timedelta(minutes=5),
        )

    assignments = bind_svc.list_member_assignments()
    assert len(assignments.members) == 1
    assert assignments.members[0].member_id == "sriram"
    assert [d.tag_id for d in assignments.members[0].devices] == ["pw5-ble", "pw5-uwb"]

    # Both tag_ids appear in site-config and resolve to the same member_id.
    cfg = site_svc.build_site_config()
    by_tag = {b.tag_id: b.member_id for b in cfg.bindings}
    assert by_tag == {"pw5-ble": "sriram", "pw5-uwb": "sriram"}


def test_unbind_and_rebind_preserve_history_and_reject_overlap(db_factory) -> None:
    _seed_floor_plan_and_members(db_factory)
    t0 = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=3)
    t2 = t1 + timedelta(hours=2)

    repo = SqlAlchemyWearableRepository(db_factory)
    dev_svc = WearableDeviceService(repo, clock=lambda: t0)
    bind_svc = WearableBindingService(repo, clock=lambda: t0)

    band = dev_svc.create_device(
        WearableDeviceCreate(
            tag_id="band-1",
            device_kind=DeviceKind.BLE_BEACON,
            label="Wristband 1",
            adapter_id="ble-home",
            hardware_key="uuid:1:1",
        ),
        actor="Admin",
    )

    b1 = bind_svc.bind(band.id, "amma", consent_recorded_by="Sriram", created_by="Admin", at=t0)
    assert b1.valid_to is None

    closed = bind_svc.unbind(band.id, actor="Admin", at=t1)
    assert closed.valid_to == t1

    # Overlap with closed interval [t0, t1) is rejected by the GiST exclusion constraint.
    with pytest.raises(ConflictError):
        bind_svc.bind(
            band.id,
            "sriram",
            consent_recorded_by="Sriram",
            created_by="Admin",
            at=t0 + timedelta(hours=1),
        )

    # Re-binding at t1 (exclusive end of previous interval) succeeds and preserves history.
    b2 = bind_svc.bind(band.id, "sriram", consent_recorded_by="Sriram", created_by="Admin", at=t1)
    assert b2.valid_from == t1

    assert bind_svc.active_binding_at(band.id, t0 - timedelta(seconds=1)) is None
    assert bind_svc.active_binding_at(band.id, t0).member_id == "amma"  # type: ignore[union-attr]
    assert bind_svc.active_binding_at(band.id, t1).member_id == "sriram"  # type: ignore[union-attr]
    assert bind_svc.active_binding_at(band.id, t2).member_id == "sriram"  # type: ignore[union-attr]

    history = bind_svc.list_history(band.id)
    assert len(history) == 2
    assert history[0].member_id == "sriram"
    assert history[1].member_id == "amma"


def test_rf_nodes_site_config_matches_room_polygon_conversion_and_survey_check(db_factory) -> None:
    room_id = _seed_floor_plan_and_members(db_factory)
    repo = SqlAlchemyWearableRepository(db_factory)
    node_svc = RfNodeService(repo)
    site_svc = WearableSiteConfigService(repo)

    # Floor plan is 1000x800 px at 0.01 m/px => 10.0 m x 8.0 m.
    # Normalized point (0.25, 0.5) must convert to (2.5 m, 4.0 m), identical to room polygons.
    ble_node = node_svc.create_node(
        RfNodeCreate(
            anchor_id="node-lr-ble",
            label="Living Room Receiver",
            adapter_id="ble-home",
            node_role=RfNodeRole.RECEIVER,
            technology=RangingTechnology.BLE_RSSI,
            room_id=room_id,
            x_norm=0.25,
            y_norm=0.5,
            z_m=1.2,
        ),
        actor="Admin",
    )
    uwb_node = node_svc.create_node(
        RfNodeCreate(
            anchor_id="node-lr-uwb",
            label="Living Room UWB Anchor",
            adapter_id="uwb-watch",
            node_role=RfNodeRole.RANGING_ANCHOR,
            technology=RangingTechnology.UWB,
            room_id=room_id,
            x_norm=0.75,
            y_norm=0.5,
            z_m=2.0,
            uwb_address_hex="00:01",
        ),
        actor="Admin",
    )
    assert ble_node.x_m == pytest.approx(2.5)
    assert ble_node.y_m == pytest.approx(4.0)
    # UWB defaults applied automatically.
    assert uwb_node.uwb_channel == 9
    assert uwb_node.uwb_preamble_index == 10

    cfg_v1 = site_svc.build_site_config()
    assert cfg_v1.floor_plan_id == "floor-plans/test.png"
    assert len(cfg_v1.nodes) == 2
    by_id = {n.anchor_id: n for n in cfg_v1.nodes}
    assert by_id["node-lr-ble"].x_m == pytest.approx(2.5)
    assert by_id["node-lr-ble"].y_m == pytest.approx(4.0)
    assert by_id["node-lr-ble"].room_id == str(room_id)
    assert by_id["node-lr-uwb"].uwb_address_hex == "00:01"
    assert by_id["node-lr-uwb"].uwb_channel == 9
    assert by_id["node-lr-uwb"].uwb_preamble_index == 10

    # Changing floor-plan scale changes site-config version hash and coordinates.
    with db_factory() as db:
        hs = db.get(HouseholdSettings, 1)
        assert hs is not None
        hs.floor_meters_per_pixel = 0.02  # 20.0 m x 16.0 m
        db.commit()

    cfg_v2 = site_svc.build_site_config()
    assert cfg_v2.version != cfg_v1.version
    assert {n.anchor_id: n.x_m for n in cfg_v2.nodes}["node-lr-ble"] == pytest.approx(5.0)

    # Restore scale to 10x8 m and check survey distance verification (<= 0.2 m ok, > 0.2 m warns).
    with db_factory() as db:
        hs = db.get(HouseholdSettings, 1)
        assert hs is not None
        hs.floor_meters_per_pixel = 0.01
        db.commit()

    ok_survey = node_svc.survey_check(
        RfNodeSurveyCheckRequest(
            x_norm=0.25,
            y_norm=0.5,
            z_m=1.2,
            measurements=[
                SurveyDistanceMeasurement(
                    reference_kind="wall", reference_id="left", measured_m=2.55
                ),
                SurveyDistanceMeasurement(
                    reference_kind="wall", reference_id="top", measured_m=3.95
                ),
            ],
        )
    )
    assert ok_survey.warning is False
    assert ok_survey.max_discrepancy_m == pytest.approx(0.05)

    bad_survey = node_svc.survey_check(
        RfNodeSurveyCheckRequest(
            x_norm=0.25,
            y_norm=0.5,
            z_m=1.2,
            measurements=[
                SurveyDistanceMeasurement(
                    reference_kind="wall", reference_id="left", measured_m=3.1
                ),
                SurveyDistanceMeasurement(
                    reference_kind="node", reference_id="node-lr-uwb", measured_m=5.06
                ),
            ],
        )
    )
    assert bad_survey.warning is True
    assert bad_survey.checks[0].exceeds_tolerance is True
    assert bad_survey.checks[1].exceeds_tolerance is False


def test_rf_node_creation_blocked_without_floor_plan(db_factory) -> None:
    repo = SqlAlchemyWearableRepository(db_factory)
    node_svc = RfNodeService(repo)
    with pytest.raises(ValidationError, match="floor plan"):
        node_svc.create_node(
            RfNodeCreate(
                anchor_id="node-no-plan",
                label="Orphan",
                adapter_id="ble-home",
                node_role=RfNodeRole.RECEIVER,
                technology=RangingTechnology.BLE_RSSI,
                x_norm=0.5,
                y_norm=0.5,
                z_m=1.0,
            ),
            actor="Admin",
        )


def test_device_deactivation_and_wearables_readiness_rules(db_factory) -> None:
    _seed_floor_plan_and_members(db_factory)
    repo = SqlAlchemyWearableRepository(db_factory)
    dev_svc = WearableDeviceService(repo)
    created = dev_svc.create_device(
        WearableDeviceCreate(
            tag_id="tag-deact",
            device_kind=DeviceKind.UWB_TAG,
            label="Clip",
            adapter_id="uwb-anchors",
            hardware_key="uwb-clip-1",
        ),
        actor="Admin",
    )
    updated = dev_svc.update_device(
        created.id,
        WearableDeviceUpdate(is_active=False),
        actor="Admin",
    )
    assert updated.is_active is False

    # Readiness rules: unconfigured is ready & optional; low battery triggers attention.
    empty_step = wearables_step(
        WearablesHealth(0, 0, 0, 0, None),
        has_floor_plan_and_scale=False,
    )
    assert empty_step.state == "ready"
    assert empty_step.optional is True

    low_batt_step = wearables_step(
        WearablesHealth(
            active_node_count=2,
            active_device_count=1,
            active_binding_count=1,
            low_battery_count=1,
            last_heard_age_s=12.0,
        ),
        has_floor_plan_and_scale=True,
    )
    assert low_batt_step.state == "attention"
    assert low_batt_step.next_action == "configure_wearables"
    assert low_batt_step.optional is True


async def test_rf_node_firmware_version_and_live_last_heard(db_factory) -> None:
    room_id = _seed_floor_plan_and_members(db_factory)
    t0 = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)

    class _FakeRfIngress:
        configured = True

        async def get_health(self):
            return RfIngressHealthInfo(
                status="ok",
                node_last_seen_age_s={"node-lr-ble": 12.5},
                tag_last_seen_age_s={"band-1": 4.0},
                tag_battery_fraction={"band-1": 0.72},
            )

    repo = SqlAlchemyWearableRepository(db_factory)
    node_svc = RfNodeService(repo, rf_ingress=_FakeRfIngress(), clock=lambda: t0)  # type: ignore[arg-type]

    created = node_svc.create_node(
        RfNodeCreate(
            anchor_id="node-lr-ble",
            label="Living Room Receiver",
            adapter_id="ble-home",
            node_role=RfNodeRole.RECEIVER,
            technology=RangingTechnology.BLE_RSSI,
            room_id=room_id,
            x_norm=0.25,
            y_norm=0.5,
            z_m=1.2,
            firmware_version="ESPresense 3.3.2",
        ),
        actor="Admin",
    )
    assert created.firmware_version == "ESPresense 3.3.2"

    live_list = await node_svc.list_nodes_live()
    assert live_list.total == 1
    assert live_list.items[0].firmware_version == "ESPresense 3.3.2"
    assert live_list.items[0].last_heard_age_s == pytest.approx(12.5)
    assert live_list.items[0].last_heard_at == t0 - timedelta(seconds=12.5)

    live_one = await node_svc.get_node_live(created.id)
    assert live_one.last_heard_at == t0 - timedelta(seconds=12.5)

    patched = node_svc.update_node(
        created.id,
        RfNodeUpdate(firmware_version="ESPresense 3.3.3"),
        actor="Admin",
    )
    assert patched.firmware_version == "ESPresense 3.3.3"


def test_wearables_readiness_step_reports_nodes_heard_tags_and_lowest_battery() -> None:
    healthy = wearables_step(
        WearablesHealth(
            active_node_count=4,
            active_device_count=2,
            active_binding_count=2,
            low_battery_count=0,
            last_heard_age_s=6.0,
            nodes_heard_recent_count=3,
            tags_heard_count=2,
            lowest_battery_fraction=0.64,
        ),
        has_floor_plan_and_scale=True,
    )
    assert healthy.state == "ready"
    assert "3 of 4 RF nodes heard in the last 5 minutes" in healthy.detail
    assert "2 of 2 tags heard" in healthy.detail
    assert "lowest beacon battery 64%" in healthy.detail

    silent_nodes = wearables_step(
        WearablesHealth(
            active_node_count=3,
            active_device_count=1,
            active_binding_count=1,
            low_battery_count=0,
            last_heard_age_s=None,
            nodes_heard_recent_count=0,
            tags_heard_count=0,
            lowest_battery_fraction=None,
        ),
        has_floor_plan_and_scale=True,
    )
    assert silent_nodes.state == "attention"
    assert "0 of 3 RF nodes heard in the last 5 minutes" in silent_nodes.detail
