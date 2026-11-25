"""Add nullable physical_device_id to wearable_devices.

Several logical tags can be one radio: a dual-mode watch registers a BLE tag and a
UWB tag. Tags that share a ``physical_device_id`` are the same physical device, so
CTS keeps one association segment across them and never reads their room
disagreement as two separated wearables. Nullable: a single-tag device leaves it
empty and is its own group.

Revision ID: 0010_wearable_physical_device_id
Revises: 0009_companion_surface_device_state
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_wearable_physical_device_id"
down_revision: str | Sequence[str] | None = "0009_companion_surface_device_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wearable_devices",
        sa.Column("physical_device_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_wearable_devices_physical_device_id",
        "wearable_devices",
        ["physical_device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_wearable_devices_physical_device_id", table_name="wearable_devices")
    op.drop_column("wearable_devices", "physical_device_id")
