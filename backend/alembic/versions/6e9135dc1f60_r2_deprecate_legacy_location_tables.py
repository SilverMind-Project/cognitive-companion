"""R2: deprecate person_location_state and person_location_history tables.

These tables are superseded by PersonLocationService (location_observations
+ presence_segments).  The four CTS filters (room, room_transition,
person_presence, scene_trend) no longer read them (R2 W2).

The tables CANNOT be dropped yet because the pre-CTS presence fusion chain
still reads them:
- services/presence/providers/cts_location.py reads PersonLocationState
  (written by services/cts/location_writer.py via CTSRuntime)
- services/presence/providers/night_anchor.py reads PersonLocationState
- services/presence/providers/stale_fallback.py reads PersonLocationState

Next step: migrate those three providers to read from PersonLocationService
(where_is / presence_history), then remove LocationWriter from CTSRuntime,
then replace this no-op with the actual drop.

DO NOT write new code that reads or writes these tables.
An import-linter contract (backend/pyproject.toml) prevents filters and
steps from reintroducing direct imports of location_repository.

Revision ID: 6e9135dc1f60
Revises: 0018_unified_location
Create Date: 2026-05-28
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6e9135dc1f60"
down_revision: str | None = "0018_unified_location"
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
