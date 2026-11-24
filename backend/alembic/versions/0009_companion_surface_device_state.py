"""Add the device state a companion surface reports on its heartbeat.

``platform`` says whether the surface runs the browser companion or the native
Android tablet / TV shell; the three capture flags are the device's own report of
its microphone, camera, and screen, so a caregiver can see a microphone that was
left on. All nullable: a browser surface never reports them.

Revision ID: 0009_companion_surface_device_state
Revises: 0008_rf_node_firmware_version
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_companion_surface_device_state"
down_revision: str | Sequence[str] | None = "0008_rf_node_firmware_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companion_surfaces", sa.Column("platform", sa.String(length=32), nullable=True))
    op.add_column("companion_surfaces", sa.Column("mic_active", sa.Boolean(), nullable=True))
    op.add_column("companion_surfaces", sa.Column("camera_active", sa.Boolean(), nullable=True))
    op.add_column("companion_surfaces", sa.Column("screen_awake", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("companion_surfaces", "screen_awake")
    op.drop_column("companion_surfaces", "camera_active")
    op.drop_column("companion_surfaces", "mic_active")
    op.drop_column("companion_surfaces", "platform")
