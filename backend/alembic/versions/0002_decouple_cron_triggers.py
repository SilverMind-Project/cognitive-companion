"""Decouple cron triggers from rules.

Replace Rule.trigger_type (single string) with Rule.trigger_types (JSON list).
Replace Rule.schedule_cron with CronTrigger + RuleCronTrigger join table.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_decouple_cron_triggers"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create cron_triggers table
    op.create_table(
        "cron_triggers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("expression", sa.String(length=128), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. Create rule_cron_triggers join table
    op.create_table(
        "rule_cron_triggers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("rules.id"), nullable=False),
        sa.Column("cron_trigger_id", sa.Integer(), sa.ForeignKey("cron_triggers.id"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rule_cron_triggers_rule_id", "rule_cron_triggers", ["rule_id"])
    op.create_index("ix_rule_cron_triggers_cron_trigger_id", "rule_cron_triggers", ["cron_trigger_id"])

    # 3. Migrate existing schedule_cron values to CronTrigger rows
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id, name, schedule_cron FROM rules WHERE schedule_cron IS NOT NULL")
    ).fetchall()
    for rule_id, rule_name, cron_expr in existing:
        result = conn.execute(
            sa.text(
                "INSERT INTO cron_triggers (name, expression, timezone) "
                "VALUES (:name, :expression, 'UTC') RETURNING id"
            ),
            {"name": f"{rule_name} (auto-migrated)", "expression": cron_expr},
        )
        ct_id = result.fetchone()[0]
        conn.execute(
            sa.text(
                "INSERT INTO rule_cron_triggers (rule_id, cron_trigger_id) VALUES (:rule_id, :ct_id)"
            ),
            {"rule_id": rule_id, "ct_id": ct_id},
        )

    # 4. Replace trigger_type column with trigger_types JSON column
    #    Migrate existing values: old single string → JSON list
    op.execute(
        sa.text(
            "ALTER TABLE rules ADD COLUMN trigger_types JSON NOT NULL DEFAULT '[\"sensor_event\"]'"
        )
    )
    rows = conn.execute(sa.text("SELECT id, trigger_type FROM rules")).fetchall()
    for rule_id, old_type in rows:
        conn.execute(
            sa.text("UPDATE rules SET trigger_types = :types WHERE id = :id"),
            {"types": f'["{old_type}"]', "id": rule_id},
        )
    op.drop_column("rules", "trigger_type")

    # 5. Drop schedule_cron column
    op.drop_column("rules", "schedule_cron")


def downgrade() -> None:
    # 1. Restore schedule_cron column
    op.add_column("rules", sa.Column("schedule_cron", sa.String(length=128), nullable=True))

    # 2. Restore trigger_type column
    op.add_column(
        "rules",
        sa.Column("trigger_type", sa.String(length=32), nullable=False, server_default="sensor_event"),
    )

    # 3. Migrate data back from JSON list
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, trigger_types FROM rules")).fetchall()
    for rule_id, types_json in rows:
        import json
        types_list = json.loads(types_json) if isinstance(types_json, str) else (types_json or ["sensor_event"])
        old_type = types_list[0] if types_list else "sensor_event"
        conn.execute(
            sa.text("UPDATE rules SET trigger_type = :t WHERE id = :id"),
            {"t": old_type, "id": rule_id},
        )
    op.alter_column("rules", "trigger_type", server_default=None)
    op.drop_column("rules", "trigger_types")

    # 4. Migrate cron_triggers back to schedule_cron (first expression only per rule)
    ct_rows = conn.execute(
        sa.text(
            "SELECT r.id, ct.expression FROM rules r "
            "JOIN rule_cron_triggers rct ON rct.rule_id = r.id "
            "JOIN cron_triggers ct ON ct.id = rct.cron_trigger_id"
        )
    ).fetchall()
    for rule_id, cron_expr in ct_rows:
        conn.execute(
            sa.text("UPDATE rules SET schedule_cron = :expr WHERE id = :id"),
            {"expr": cron_expr, "id": rule_id},
        )

    # 5. Drop join table and cron_triggers
    op.drop_index("ix_rule_cron_triggers_cron_trigger_id", table_name="rule_cron_triggers")
    op.drop_index("ix_rule_cron_triggers_rule_id", table_name="rule_cron_triggers")
    op.drop_table("rule_cron_triggers")
    op.drop_table("cron_triggers")
