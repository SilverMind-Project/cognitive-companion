"""Wearable device registry, time-bounded bindings, and fixed RF node models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base, TimestampMixin
from backend.core.time import UTCDateTime


class WearableDevice(Base, TimestampMixin):
    """Registered wearable device identified by a hardware-neutral ``tag_id``.

    ``hardware_key`` is the opaque identifier observed on the air by ``adapter_id``
    (for example an iBeacon UUID/major/minor string or a UWB tag identifier) and is
    the only place a radio identifier is stored.
    """

    __tablename__ = "wearable_devices"
    __table_args__ = (
        CheckConstraint(
            "device_kind IN ('ble_beacon', 'watch', 'uwb_tag')",
            name="ck_wearable_devices_kind",
        ),
        CheckConstraint(
            "last_battery_fraction IS NULL OR "
            "(last_battery_fraction >= 0.0 AND last_battery_fraction <= 1.0)",
            name="ck_wearable_devices_battery_fraction",
        ),
        UniqueConstraint(
            "adapter_id",
            "hardware_key",
            name="uq_wearable_devices_adapter_hardware_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    device_kind: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    hardware_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    last_heard_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_battery_fraction: Mapped[float | None] = mapped_column(Double, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    bindings: Mapped[list[WearableBinding]] = relationship(back_populates="device")


class WearableBinding(Base):
    """Time-bounded, consented binding of a wearable device to a household member.

    Bindings are immutable intervals ``[valid_from, valid_to)``: re-binding a device
    closes the previous binding and opens a new row so historical fixes stay
    interpretable. One member may hold several active bindings at once; one device
    may never hold overlapping bindings (enforced by a Postgres GiST exclusion
    constraint). When a member is deleted, active bindings are closed first and the
    foreign key sets ``member_id`` to ``NULL`` to preserve anonymized audit history.
    """

    __tablename__ = "wearable_bindings"
    __table_args__ = (
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_wearable_bindings_valid_range",
        ),
        CheckConstraint(
            "valid_to IS NOT NULL OR member_id IS NOT NULL",
            name="ck_wearable_bindings_active_has_member",
        ),
        ExcludeConstraint(
            ("device_id", "="),
            (
                text("tstzrange(valid_from, COALESCE(valid_to, 'infinity'::timestamptz), '[)')"),
                "&&",
            ),
            name="excl_wearable_bindings_no_overlap",
            using="gist",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wearable_devices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("household_members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    consent_recorded_by: Mapped[str] = mapped_column(Text, nullable=False)
    consent_recorded_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)

    device: Mapped[WearableDevice] = relationship(back_populates="bindings")


class RfNode(Base, TimestampMixin):
    """Fixed RF node (room receiver or ranging anchor) placed on the household floor plan.

    ``x_norm`` and ``y_norm`` are normalized floor-plan coordinates in ``[0, 1]``
    matching room polygons; ``z_m`` is mount height above the floor in metres
    (``[0, 4]``). Optional UWB parameters apply when ``technology = 'uwb'``.
    """

    __tablename__ = "rf_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_role IN ('receiver', 'ranging_anchor')",
            name="ck_rf_nodes_role",
        ),
        CheckConstraint(
            "technology IN ('ble_rssi', 'ble_channel_sounding', 'uwb')",
            name="ck_rf_nodes_technology",
        ),
        CheckConstraint("x_norm >= 0.0 AND x_norm <= 1.0", name="ck_rf_nodes_x_norm"),
        CheckConstraint("y_norm >= 0.0 AND y_norm <= 1.0", name="ck_rf_nodes_y_norm"),
        CheckConstraint("z_m >= 0.0 AND z_m <= 4.0", name="ck_rf_nodes_z_m"),
        CheckConstraint(
            "placement_residual_m IS NULL OR placement_residual_m >= 0.0",
            name="ck_rf_nodes_placement_residual",
        ),
        CheckConstraint(
            "uwb_address_hex IS NULL OR uwb_address_hex ~ '^[0-9a-fA-F]{2}:[0-9a-fA-F]{2}$'",
            name="ck_rf_nodes_uwb_address_hex",
        ),
        CheckConstraint(
            "uwb_channel IS NULL OR uwb_channel IN (5, 9)",
            name="ck_rf_nodes_uwb_channel",
        ),
        CheckConstraint(
            "uwb_preamble_index IS NULL OR (uwb_preamble_index >= 9 AND uwb_preamble_index <= 32)",
            name="ck_rf_nodes_uwb_preamble_index",
        ),
        Index(
            "uix_rf_nodes_active_uwb_address",
            text("lower(uwb_address_hex)"),
            unique=True,
            postgresql_where=text(
                "is_active = true AND technology = 'uwb' AND uwb_address_hex IS NOT NULL"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anchor_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    adapter_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    node_role: Mapped[str] = mapped_column(Text, nullable=False)
    technology: Mapped[str] = mapped_column(Text, nullable=False)
    room_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("rooms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    x_norm: Mapped[float] = mapped_column(Double, nullable=False)
    y_norm: Mapped[float] = mapped_column(Double, nullable=False)
    z_m: Mapped[float] = mapped_column(Double, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    placement_residual_m: Mapped[float | None] = mapped_column(Double, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uwb_address_hex: Mapped[str | None] = mapped_column(String(8), nullable=True)
    uwb_channel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uwb_preamble_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )
