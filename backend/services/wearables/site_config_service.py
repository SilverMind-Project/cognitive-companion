"""Service building the hardware-neutral site-config payload and readiness summary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from cts_contracts import DeviceKind, RangingTechnology, RfNodeRole

from backend.schemas.wearables import (
    SiteConfigBindingOut,
    SiteConfigDeviceOut,
    SiteConfigNodeOut,
    WearableSiteConfigOut,
)
from backend.services.floor_plan_geometry import floor_plan_scale, norm_to_floor_m
from backend.services.wearables.repositories import SqlAlchemyWearableRepository

LOW_BATTERY_THRESHOLD = 0.2


@dataclass(frozen=True)
class WearablesReadinessSnapshot:
    """Counts and freshness summary fed into ``IdentityReadinessService``."""

    active_node_count: int
    active_device_count: int
    active_binding_count: int
    low_battery_count: int
    last_heard_age_s: float | None
    active_node_anchor_ids: tuple[str, ...] = ()
    active_device_tag_ids: tuple[str, ...] = ()
    device_heard_tag_ids: tuple[str, ...] = ()
    device_battery_by_tag_id: tuple[tuple[str, float], ...] = ()
    lowest_battery_fraction: float | None = None


class WearableSiteConfigService:
    """Produces ``GET /api/v1/wearables/site-config`` for CTS and rf-ingress."""

    def __init__(
        self,
        repo: SqlAlchemyWearableRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._clock = clock

    def build_site_config(self) -> WearableSiteConfigOut:
        """Build the site-config snapshot with metres from the shared floor-plan helper.

        ``version`` is a deterministic SHA-256 hash of the canonical JSON payload
        (including ``floor_plan_id``, metres, bindings, and devices) so any scale,
        node, device, or binding change yields a new version string.
        """
        with self._repo.session() as db:
            settings = self._repo.get_household_settings(db)
            scale = floor_plan_scale(settings)
            devices = self._repo.list_devices(db)
            devices_by_id = {d.id: d for d in devices}

            nodes_out: list[SiteConfigNodeOut] = []
            if scale is not None:
                for node in self._repo.list_nodes(db, active_only=True):
                    x_m, y_m = norm_to_floor_m(node.x_norm, node.y_norm, scale)
                    nodes_out.append(
                        SiteConfigNodeOut(
                            anchor_id=node.anchor_id,
                            adapter_id=node.adapter_id,
                            node_role=RfNodeRole(node.node_role),
                            technology=RangingTechnology(node.technology),
                            x_m=round(x_m, 6),
                            y_m=round(y_m, 6),
                            z_m=round(float(node.z_m), 6),
                            room_id=str(node.room_id) if node.room_id is not None else None,
                            uwb_address_hex=node.uwb_address_hex,
                            uwb_channel=node.uwb_channel,
                            uwb_preamble_index=node.uwb_preamble_index,
                        )
                    )

            bindings_out: list[SiteConfigBindingOut] = []
            for binding in self._repo.list_all_bindings(db, non_null_member_only=True):
                if binding.member_id is None:
                    continue
                device = devices_by_id.get(binding.device_id)
                if device is None:
                    continue
                bindings_out.append(
                    SiteConfigBindingOut(
                        tag_id=device.tag_id,
                        member_id=binding.member_id,
                        valid_from=binding.valid_from.astimezone(UTC),
                        valid_to=(
                            binding.valid_to.astimezone(UTC)
                            if binding.valid_to is not None
                            else None
                        ),
                    )
                )

            devices_out = [
                SiteConfigDeviceOut(
                    tag_id=d.tag_id,
                    adapter_id=d.adapter_id,
                    hardware_key=d.hardware_key,
                    device_kind=DeviceKind(d.device_kind),
                    is_active=d.is_active,
                    physical_device_id=d.physical_device_id,
                )
                for d in devices
            ]

            floor_plan_id = scale.floor_plan_id if scale is not None else None
            canonical = {
                "floor_plan_id": floor_plan_id,
                "nodes": [n.model_dump(mode="json") for n in nodes_out],
                "bindings": [b.model_dump(mode="json") for b in bindings_out],
                "devices": [d.model_dump(mode="json") for d in devices_out],
            }
            digest = hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16]

            return WearableSiteConfigOut(
                floor_plan_id=floor_plan_id,
                nodes=nodes_out,
                bindings=bindings_out,
                devices=devices_out,
                version=f"sha256:{digest}",
            )

    def readiness_snapshot(self) -> WearablesReadinessSnapshot:
        """Return counts and last-heard age for the unified identity readiness surface."""
        now = self._clock()
        with self._repo.session() as db:
            active_nodes = self._repo.list_nodes(db, active_only=True)
            active_devices = self._repo.list_devices(db, active_only=True)
            active_bindings = self._repo.list_all_bindings(
                db, active_only=True, non_null_member_only=True
            )
            batteries = [
                (d.tag_id, float(d.last_battery_fraction))
                for d in active_devices
                if d.last_battery_fraction is not None
            ]
            low_battery = sum(1 for _, frac in batteries if frac < LOW_BATTERY_THRESHOLD)
            lowest_battery = min((frac for _, frac in batteries), default=None)
            heard_tags = tuple(d.tag_id for d in active_devices if d.last_heard_at is not None)
            heard_times = [
                d.last_heard_at.astimezone(UTC)
                for d in active_devices
                if d.last_heard_at is not None
            ]
            last_age_s: float | None = None
            if heard_times:
                newest = max(heard_times)
                last_age_s = max(0.0, (now - newest).total_seconds())
            return WearablesReadinessSnapshot(
                active_node_count=len(active_nodes),
                active_device_count=len(active_devices),
                active_binding_count=len(active_bindings),
                low_battery_count=low_battery,
                last_heard_age_s=last_age_s,
                active_node_anchor_ids=tuple(n.anchor_id for n in active_nodes),
                active_device_tag_ids=tuple(d.tag_id for d in active_devices),
                device_heard_tag_ids=heard_tags,
                device_battery_by_tag_id=tuple(batteries),
                lowest_battery_fraction=lowest_battery,
            )
