"""R2: deprecate person_location_state and person_location_history tables.

These tables are superseded by PersonLocationService (location_observations
+ presence_segments).  The CTS filters no longer read them (R2 W2).

The tables CANNOT be dropped yet because the pre-CTS presence providers
still depend on them:
- services/presence/providers/cts_location.py
- services/presence/providers/night_anchor.py
- services/presence/providers/stale_fallback.py

Once those providers are migrated to read from PersonLocationService,
this migration will be amended to:
  - upgrade(): drop person_location_state, person_location_history
  - downgrade(): recreate them with the original 0001 schema.

For now, this is a no-op that documents the dependency.

Revision ID: 6e9135dc1f60
Revises: 990462f4cf44
Create Date: 2026-05-28
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6e9135dc1f60"
down_revision: str | None = "990462f4cf44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: tables still needed by presence providers.

    When ready to drop, replace with:
        op.drop_table("person_location_state")
        op.drop_table("person_location_history")
    """


def downgrade() -> None:
    """No-op: nothing to undo."""
