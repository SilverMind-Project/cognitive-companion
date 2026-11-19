"""Service for managing hardware-neutral wearable devices and their reporting status."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from cts_contracts import DeviceKind
from sqlalchemy.exc import IntegrityError

from backend.core.exceptions import ConflictError, NotFoundError
from backend.core.logging import get_logger
from backend.models.wearable import WearableBinding, WearableDevice
from backend.schemas.wearables import (
    WearableBindingOut,
    WearableDeviceCreate,
    WearableDeviceListOut,
    WearableDeviceOut,
    WearableDeviceStatusOut,
    WearableDeviceUpdate,
)
from backend.services.wearables.repositories import SqlAlchemyWearableRepository

logger = get_logger(__name__)

# A device heard within this window is reported as actively reporting.
REPORTING_MAX_AGE_S = 300.0


def _binding_out(
    binding: WearableBinding | None,
    *,
    tag_id: str,
    member_names: dict[str, str],
) -> WearableBindingOut | None:
    if binding is None:
        return None
    return WearableBindingOut(
        id=binding.id,
        device_id=binding.device_id,
        tag_id=tag_id,
        member_id=binding.member_id,
        member_name=member_names.get(binding.member_id) if binding.member_id else None,
        valid_from=binding.valid_from,
        valid_to=binding.valid_to,
        consent_recorded_by=binding.consent_recorded_by,
        consent_recorded_at=binding.consent_recorded_at,
        created_by=binding.created_by,
    )


def _device_out(
    device: WearableDevice,
    *,
    active_binding: WearableBinding | None,
    member_names: dict[str, str],
) -> WearableDeviceOut:
    return WearableDeviceOut(
        id=device.id,
        tag_id=device.tag_id,
        device_kind=DeviceKind(device.device_kind),
        label=device.label,
        adapter_id=device.adapter_id,
        hardware_key=device.hardware_key,
        is_active=device.is_active,
        last_heard_at=device.last_heard_at,
        last_battery_fraction=device.last_battery_fraction,
        active_binding=_binding_out(active_binding, tag_id=device.tag_id, member_names=member_names),
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


class WearableDeviceService:
    """CRUD and live reporting status for registered wearable devices."""

    def __init__(
        self,
        repo: SqlAlchemyWearableRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._clock = clock

    def list_devices(self, *, active_only: bool = False) -> WearableDeviceListOut:
        with self._repo.session() as db:
            devices = self._repo.list_devices(db, active_only=active_only)
            active_bindings = {
                b.device_id: b for b in self._repo.list_all_bindings(db, active_only=True)
            }
            member_names = {mid: m.name for mid, m in self._repo.list_members_map(db).items()}
            items = [
                _device_out(
                    d,
                    active_binding=active_bindings.get(d.id),
                    member_names=member_names,
                )
                for d in devices
            ]
            return WearableDeviceListOut(items=items, total=len(items))

    def get_device(self, device_id: uuid.UUID) -> WearableDeviceOut:
        with self._repo.session() as db:
            device = self._repo.get_device(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            binding = self._repo.active_binding_for_device(db, device.id)
            member_names = {mid: m.name for mid, m in self._repo.list_members_map(db).items()}
            return _device_out(device, active_binding=binding, member_names=member_names)

    def create_device(self, payload: WearableDeviceCreate, *, actor: str) -> WearableDeviceOut:
        now = self._clock()
        with self._repo.session() as db:
            device = WearableDevice(
                id=uuid.uuid4(),
                tag_id=payload.tag_id,
                device_kind=payload.device_kind.value,
                label=payload.label,
                adapter_id=payload.adapter_id,
                hardware_key=payload.hardware_key,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(device)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError(
                    "A wearable device with that tag_id or (adapter_id, hardware_key) already exists"
                ) from exc
            db.refresh(device)
            logger.info(
                "wearable_device_created",
                device_id=str(device.id),
                tag_id=device.tag_id,
                device_kind=device.device_kind,
                adapter_id=device.adapter_id,
                actor=actor,
            )
            return _device_out(device, active_binding=None, member_names={})

    def update_device(
        self,
        device_id: uuid.UUID,
        payload: WearableDeviceUpdate,
        *,
        actor: str,
    ) -> WearableDeviceOut:
        now = self._clock()
        with self._repo.session() as db:
            device = self._repo.get_device(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            updates = payload.model_dump(exclude_unset=True)
            for key, value in updates.items():
                if key == "device_kind" and isinstance(value, DeviceKind):
                    setattr(device, key, value.value)
                else:
                    setattr(device, key, value)
            device.updated_at = now
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError(
                    "Updating wearable device conflicts with an existing (adapter_id, hardware_key)"
                ) from exc
            db.refresh(device)
            binding = self._repo.active_binding_for_device(db, device.id)
            member_names = {mid: m.name for mid, m in self._repo.list_members_map(db).items()}
            logger.info(
                "wearable_device_updated",
                device_id=str(device.id),
                tag_id=device.tag_id,
                is_active=device.is_active,
                actor=actor,
            )
            return _device_out(device, active_binding=binding, member_names=member_names)

    def get_device_status(self, device_id: uuid.UUID) -> WearableDeviceStatusOut:
        with self._repo.session() as db:
            device = self._repo.get_device(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            return self._build_status(db, device)

    def get_device_status_by_tag(self, tag_id: str) -> WearableDeviceStatusOut:
        with self._repo.session() as db:
            device = self._repo.get_device_by_tag_id(db, tag_id)
            if device is None:
                raise NotFoundError("WearableDevice", tag_id)
            return self._build_status(db, device)

    def _build_status(self, db, device: WearableDevice) -> WearableDeviceStatusOut:
        now = self._clock()
        binding = self._repo.active_binding_for_device(db, device.id)
        member_name: str | None = None
        if binding is not None and binding.member_id is not None:
            member = self._repo.get_member(db, binding.member_id)
            member_name = member.name if member is not None else None
        age_s: float | None = None
        reporting = False
        if device.last_heard_at is not None:
            age_s = max(0.0, (now - device.last_heard_at.astimezone(UTC)).total_seconds())
            reporting = device.is_active and age_s <= REPORTING_MAX_AGE_S
        return WearableDeviceStatusOut(
            device_id=device.id,
            tag_id=device.tag_id,
            label=device.label,
            device_kind=DeviceKind(device.device_kind),
            adapter_id=device.adapter_id,
            is_active=device.is_active,
            bound_member_id=binding.member_id if binding is not None else None,
            bound_member_name=member_name,
            reporting=reporting,
            last_heard_at=device.last_heard_at,
            last_heard_age_s=round(age_s, 1) if age_s is not None else None,
            last_battery_fraction=device.last_battery_fraction,
            checked_at=now,
        )
