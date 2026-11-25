"""Service for time-bounded, consented wearable bindings and member assignments."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from cts_contracts import DeviceKind
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.wearable import WearableBinding
from backend.schemas.wearables import (
    MemberWearableDeviceSummary,
    MemberWearablesOut,
    WearableAssignmentsOut,
    WearableBindingOut,
)
from backend.services.wearables.device_service import (
    _binding_out,
    _device_out,
    check_physical_device_group,
)
from backend.services.wearables.repositories import SqlAlchemyWearableRepository

logger = get_logger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValidationError("Binding timestamps must be timezone-aware")
    return dt.astimezone(UTC)


class WearableBindingService:
    """Manages immutable, non-overlapping wearable-to-member binding intervals.

    One member may hold multiple active bindings (for example a wristband plus a
    clip, or a dual-mode watch registered under both BLE and UWB adapters). One
    device may never have overlapping bindings; re-binding closes the previous
    binding or rejects overlap with ``ConflictError`` (409).
    """

    def __init__(
        self,
        repo: SqlAlchemyWearableRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._clock = clock

    def bind(
        self,
        device_id: uuid.UUID,
        member_id: str,
        *,
        consent_recorded_by: str,
        created_by: str,
        at: datetime | None = None,
    ) -> WearableBindingOut:
        """Open a new consented binding for *device_id* to *member_id* at *at*."""
        now = self._clock()
        valid_from = _to_utc(at) if at is not None else now
        consent_by = consent_recorded_by.strip()
        if not consent_by:
            raise ValidationError("consent_recorded_by is required")

        with self._repo.session() as db:
            device = self._repo.get_device_for_update(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            if not device.is_active:
                raise ValidationError("Cannot bind an inactive wearable device")

            member = self._repo.get_member(db, member_id)
            if member is None:
                raise NotFoundError("HouseholdMember", member_id)

            active = self._repo.active_binding_for_device(db, device_id)
            if active is not None:
                raise ConflictError(
                    "Wearable device already has an active binding; unbind it before re-binding"
                )
            check_physical_device_group(
                self._repo,
                db,
                device_id=device.id,
                physical_device_id=device.physical_device_id,
                adapter_id=device.adapter_id,
                member_id=member.id,
            )

            binding = WearableBinding(
                id=uuid.uuid4(),
                device_id=device.id,
                member_id=member.id,
                valid_from=valid_from,
                valid_to=None,
                consent_recorded_by=consent_by,
                consent_recorded_at=now,
                created_by=created_by,
            )
            db.add(binding)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError(
                    "Binding interval overlaps an existing binding for this wearable device"
                ) from exc
            db.refresh(binding)
            logger.info(
                "wearable_bound",
                device_id=str(device.id),
                tag_id=device.tag_id,
                member_id=member.id,
                actor=created_by,
            )
            result = _binding_out(
                binding,
                tag_id=device.tag_id,
                member_names={member.id: member.name},
            )
            assert result is not None
            return result

    def unbind(
        self,
        device_id: uuid.UUID,
        *,
        actor: str,
        at: datetime | None = None,
    ) -> WearableBindingOut:
        """Close the currently active binding for *device_id* by setting ``valid_to``."""
        end_at = _to_utc(at) if at is not None else self._clock()
        with self._repo.session() as db:
            device = self._repo.get_device_for_update(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            active = self._repo.active_binding_for_device(db, device_id)
            if active is None:
                raise ConflictError("Wearable device has no active binding to close")
            if end_at <= active.valid_from.astimezone(UTC):
                raise ValidationError("Unbind timestamp must be strictly after valid_from")

            active.valid_to = end_at
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise ConflictError("Closing binding violated interval constraints") from exc
            db.refresh(active)
            member_names = {mid: m.name for mid, m in self._repo.list_members_map(db).items()}
            logger.info(
                "wearable_unbound",
                device_id=str(device.id),
                tag_id=device.tag_id,
                member_id=active.member_id,
                actor=actor,
            )
            result = _binding_out(active, tag_id=device.tag_id, member_names=member_names)
            assert result is not None
            return result

    def active_binding_at(self, device_id: uuid.UUID, at: datetime) -> WearableBindingOut | None:
        """Return the binding covering *device_id* at timestamp *at*, or ``None``."""
        ts = _to_utc(at)
        with self._repo.session() as db:
            device = self._repo.get_device(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            binding = self._repo.binding_at(db, device_id, ts)
            if binding is None:
                return None
            member_names = {mid: m.name for mid, m in self._repo.list_members_map(db).items()}
            return _binding_out(binding, tag_id=device.tag_id, member_names=member_names)

    def list_history(self, device_id: uuid.UUID) -> list[WearableBindingOut]:
        """Return all bindings for *device_id*, newest first."""
        with self._repo.session() as db:
            device = self._repo.get_device(db, device_id)
            if device is None:
                raise NotFoundError("WearableDevice", str(device_id))
            rows = self._repo.list_bindings_for_device(db, device_id)
            member_names = {mid: m.name for mid, m in self._repo.list_members_map(db).items()}
            out: list[WearableBindingOut] = []
            for row in rows:
                item = _binding_out(row, tag_id=device.tag_id, member_names=member_names)
                if item is not None:
                    out.append(item)
            return out

    def list_member_assignments(self) -> WearableAssignmentsOut:
        """Group every currently bound wearable by household member, plus unbound devices."""
        now = self._clock()
        with self._repo.session() as db:
            devices = self._repo.list_devices(db)
            devices_by_id = {d.id: d for d in devices}
            members_map = self._repo.list_members_map(db)
            member_names = {mid: m.name for mid, m in members_map.items()}
            active_bindings = self._repo.list_all_bindings(
                db, active_only=True, non_null_member_only=True
            )
            bound_device_ids: set[uuid.UUID] = set()
            by_member: dict[str, list[MemberWearableDeviceSummary]] = {}
            for binding in active_bindings:
                if binding.member_id is None:
                    continue
                device = devices_by_id.get(binding.device_id)
                if device is None:
                    continue
                bound_device_ids.add(device.id)
                by_member.setdefault(binding.member_id, []).append(
                    MemberWearableDeviceSummary(
                        device_id=device.id,
                        tag_id=device.tag_id,
                        label=device.label,
                        device_kind=DeviceKind(device.device_kind),
                        adapter_id=device.adapter_id,
                        physical_device_id=device.physical_device_id,
                        is_active=device.is_active,
                        valid_from=binding.valid_from,
                        consent_recorded_by=binding.consent_recorded_by,
                        last_heard_at=device.last_heard_at,
                        last_battery_fraction=device.last_battery_fraction,
                    )
                )

            members_out = [
                MemberWearablesOut(
                    member_id=mid,
                    member_name=member_names.get(mid, mid),
                    devices=sorted(summaries, key=lambda s: s.tag_id),
                )
                for mid, summaries in sorted(
                    by_member.items(), key=lambda pair: member_names.get(pair[0], pair[0]).lower()
                )
            ]
            unbound_out = [
                _device_out(d, active_binding=None, member_names=member_names)
                for d in devices
                if d.id not in bound_device_ids
            ]
            return WearableAssignmentsOut(
                members=members_out,
                unbound_devices=unbound_out,
                checked_at=now,
            )

    @staticmethod
    def close_active_bindings_for_member(
        db: Session,
        member_id: str,
        *,
        at: datetime | None = None,
    ) -> int:
        """Close every open binding for *member_id* inside the caller's transaction.

        Called before deleting a ``HouseholdMember`` so the foreign key's
        ``ON DELETE SET NULL`` never hits the open-binding check constraint and
        bound tags immediately stop resolving to the deleted member.
        """
        end_at = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        rows = (
            db.query(WearableBinding)
            .filter(
                WearableBinding.member_id == member_id,
                WearableBinding.valid_to.is_(None),
            )
            .all()
        )
        for row in rows:
            start = row.valid_from.astimezone(UTC)
            row.valid_to = end_at if end_at > start else start
            if row.valid_to == start:
                # Guarantee strict valid_to > valid_from even for same-microsecond deletes.
                from datetime import timedelta

                row.valid_to = start + timedelta(microseconds=1)
        if rows:
            db.flush()
            logger.info(
                "wearable_bindings_closed_for_deleted_member",
                member_id=member_id,
                closed_count=len(rows),
            )
        return len(rows)
