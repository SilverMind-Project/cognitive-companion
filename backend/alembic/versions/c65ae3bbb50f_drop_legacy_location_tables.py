"""Drop legacy location tables

Revision ID: c65ae3bbb50f
Revises: 0015_guided_live_unique
Create Date: 2026-07-19 21:07:40.122350

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c65ae3bbb50f"
down_revision: str | Sequence[str] | None = "0015_guided_live_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("person_location_state")
    op.drop_table("person_location_history")
    op.drop_table("person_sightings")

    op.execute(
        "UPDATE location_observations SET source = 'face_sighting' WHERE source = 'recamera_vlm'"
    )
    op.execute(
        "UPDATE presence_segments SET entry_source = 'face_sighting' WHERE entry_source = 'recamera_vlm'"
    )
    op.execute(
        "UPDATE presence_segments SET exit_source = 'face_sighting' WHERE exit_source = 'recamera_vlm'"
    )


def downgrade() -> None:
    """Downgrade schema."""
