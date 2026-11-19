"""Repository protocols and SQLAlchemy implementations for wearable registry tables."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.household_settings import HouseholdSettings
from backend.models.person import HouseholdMember
from backend.models.room import Room
from backend.models.wearable import RfNode, WearableBinding, WearableDevice


class WearableRepositoryProtocol(Protocol):
    """Data-access boundary for wearable devices, bindings, RF nodes, and floor-plan scale."""

    def session(self) -> Session: ...


class SqlAlchemyWearableRepository:
    """Thin SQLAlchemy repository wrapping a session factory for wearable services."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def list_devices(db: Session, *, active_only: bool = False) -> list[WearableDevice]:
        stmt = select(WearableDevice).order_by(WearableDevice.tag_id)
        if active_only:
            stmt = stmt.where(WearableDevice.is_active.is_(True))
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_device(db: Session, device_id: uuid.UUID) -> WearableDevice | None:
        return db.get(WearableDevice, device_id)

    @staticmethod
    def get_device_for_update(db: Session, device_id: uuid.UUID) -> WearableDevice | None:
        stmt = select(WearableDevice).where(WearableDevice.id == device_id).with_for_update()
        return db.scalar(stmt)

    @staticmethod
    def get_device_by_tag_id(db: Session, tag_id: str) -> WearableDevice | None:
        stmt = select(WearableDevice).where(WearableDevice.tag_id == tag_id)
        return db.scalar(stmt)

    @staticmethod
    def list_bindings_for_device(db: Session, device_id: uuid.UUID) -> list[WearableBinding]:
        stmt = (
            select(WearableBinding)
            .where(WearableBinding.device_id == device_id)
            .order_by(WearableBinding.valid_from.desc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_all_bindings(
        db: Session, *, active_only: bool = False, non_null_member_only: bool = False
    ) -> list[WearableBinding]:
        stmt = select(WearableBinding).order_by(
            WearableBinding.device_id, WearableBinding.valid_from.asc()
        )
        if active_only:
            stmt = stmt.where(WearableBinding.valid_to.is_(None))
        if non_null_member_only:
            stmt = stmt.where(WearableBinding.member_id.is_not(None))
        return list(db.scalars(stmt).all())

    @staticmethod
    def active_binding_for_device(db: Session, device_id: uuid.UUID) -> WearableBinding | None:
        stmt = select(WearableBinding).where(
            WearableBinding.device_id == device_id,
            WearableBinding.valid_to.is_(None),
        )
        return db.scalar(stmt)

    @staticmethod
    def binding_at(db: Session, device_id: uuid.UUID, at: datetime) -> WearableBinding | None:
        ts = at.astimezone(UTC)
        stmt = select(WearableBinding).where(
            WearableBinding.device_id == device_id,
            WearableBinding.valid_from <= ts,
            (WearableBinding.valid_to.is_(None)) | (WearableBinding.valid_to > ts),
        )
        return db.scalar(stmt)

    @staticmethod
    def get_member(db: Session, member_id: str) -> HouseholdMember | None:
        return db.get(HouseholdMember, member_id)

    @staticmethod
    def list_members_map(db: Session) -> dict[str, HouseholdMember]:
        rows = db.scalars(select(HouseholdMember)).all()
        return {m.id: m for m in rows}

    @staticmethod
    def list_nodes(db: Session, *, active_only: bool = False) -> list[RfNode]:
        stmt = select(RfNode).order_by(RfNode.anchor_id)
        if active_only:
            stmt = stmt.where(RfNode.is_active.is_(True))
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_node(db: Session, node_id: uuid.UUID) -> RfNode | None:
        return db.get(RfNode, node_id)

    @staticmethod
    def get_node_by_anchor_id(db: Session, anchor_id: str) -> RfNode | None:
        stmt = select(RfNode).where(RfNode.anchor_id == anchor_id)
        return db.scalar(stmt)

    @staticmethod
    def list_rooms_map(db: Session) -> dict[int, Room]:
        rows = db.scalars(select(Room)).all()
        return {r.id: r for r in rows}

    @staticmethod
    def get_room(db: Session, room_id: int) -> Room | None:
        return db.get(Room, room_id)

    @staticmethod
    def get_household_settings(db: Session) -> HouseholdSettings | None:
        return db.get(HouseholdSettings, 1)
