"""Add guided-task routine and session tables.

RoutineStep.zone_id is intentionally nullable integer-only in this migration.
M6 creates room_zones and adds the foreign key constraint.

Revision ID: 0008_guided_task
Revises: 0007_edge_port_fanout
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from backend.core.time import UTCDateTime

revision: str = "0008_guided_task"
down_revision: str | Sequence[str] | None = "0007_edge_port_fanout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("language_override", sa.String(length=16), nullable=True),
        sa.Column("voice_override", sa.String(length=64), nullable=True),
        sa.Column("system_instruction_override", sa.Text(), nullable=True),
        sa.Column("step_timeout_s_override", sa.Integer(), nullable=True),
        sa.Column("max_step_attempts_override", sa.Integer(), nullable=True),
        sa.Column("resume_grace_s_override", sa.Integer(), nullable=True),
        sa.Column(
            "escalation_channels_override",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "summon_channels_override",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("rephrase_via_override", sa.String(length=16), nullable=True),
        sa.Column("created_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["household_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_routines_person_id"), "routines", ["person_id"], unique=False)

    op.create_table(
        "routine_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("routine_id", sa.Integer(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("completion_gate", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("skip_condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("camera_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("min_duration_s", sa.Integer(), nullable=True),
        sa.Column("step_timeout_s_override", sa.Integer(), nullable=True),
        sa.Column("max_step_attempts_override", sa.Integer(), nullable=True),
        sa.Column("is_safety_critical", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", UTCDateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("routine_id", "ord", name="uq_routine_step_ord"),
    )
    op.create_index(
        op.f("ix_routine_steps_routine_id"),
        "routine_steps",
        ["routine_id"],
        unique=False,
    )

    op.create_table(
        "guided_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("routine_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=True),
        sa.Column("surface_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step_ord", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=False),
        sa.Column("last_activity_at", UTCDateTime(), nullable=False),
        sa.Column("completed_at", UTCDateTime(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_guided_sessions_execution_id"),
        "guided_sessions",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_guided_sessions_live_person",
        "guided_sessions",
        ["person_id"],
        unique=False,
        postgresql_where=sa.text(
            "status IN ('active', 'waiting', 'summoning', 'escalated', 'caregiver_takeover')"
        ),
    )
    op.create_index(
        op.f("ix_guided_sessions_person_id"),
        "guided_sessions",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guided_sessions_routine_id"),
        "guided_sessions",
        ["routine_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guided_sessions_status"),
        "guided_sessions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "guided_session_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("at", UTCDateTime(), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("step_ord", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=24), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["guided_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_guided_session_events_at"),
        "guided_session_events",
        ["at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_guided_session_events_session_id"),
        "guided_session_events",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_guided_session_events_session_id"), table_name="guided_session_events")
    op.drop_index(op.f("ix_guided_session_events_at"), table_name="guided_session_events")
    op.drop_table("guided_session_events")
    op.drop_index(op.f("ix_guided_sessions_status"), table_name="guided_sessions")
    op.drop_index(op.f("ix_guided_sessions_routine_id"), table_name="guided_sessions")
    op.drop_index(op.f("ix_guided_sessions_person_id"), table_name="guided_sessions")
    op.drop_index("ix_guided_sessions_live_person", table_name="guided_sessions")
    op.drop_index(op.f("ix_guided_sessions_execution_id"), table_name="guided_sessions")
    op.drop_table("guided_sessions")
    op.drop_index(op.f("ix_routine_steps_routine_id"), table_name="routine_steps")
    op.drop_table("routine_steps")
    op.drop_index(op.f("ix_routines_person_id"), table_name="routines")
    op.drop_table("routines")
