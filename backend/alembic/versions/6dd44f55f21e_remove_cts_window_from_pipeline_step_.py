"""remove cts_window from pipeline step configs

Revision ID: 6dd44f55f21e
Revises: c65ae3bbb50f
Create Date: 2026-07-19 21:40:16.694387

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6dd44f55f21e"
down_revision: str | Sequence[str] | None = "c65ae3bbb50f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


import json
import logging

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, config_json FROM pipeline_steps WHERE config_json IS NOT NULL")
    ).fetchall()

    for row_id, config_val in rows:
        if isinstance(config_val, str):
            try:
                config = json.loads(config_val)
            except json.JSONDecodeError:
                continue
        elif isinstance(config_val, dict):
            # Shallow copy the dict if it's already a dict (e.g. from JSONB in pg8000 or asyncpg)
            config = dict(config_val)
        else:
            continue

        changed = False

        if "cts_frames_path" in config:
            val = config["cts_frames_path"]
            if val != "steps.media_window_poll_1.outputs.frames":
                config["pipeline_image_path"] = val
                config["image_source"] = "pipeline"
            del config["cts_frames_path"]
            changed = True

        if config.get("image_source") == "cts_window":
            config["image_source"] = "media_window"
            changed = True

        if changed:
            logger.info("Rewrote config_json for pipeline step %s", row_id)
            conn.execute(
                sa.text("UPDATE pipeline_steps SET config_json = :config WHERE id = :id"),
                {"config": json.dumps(config), "id": row_id},
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Data migration downgrade is a no-op by design (the rewritten configs are valid under the old schema too; recreating deleted cts_frames_path keys would be fabrication).
