"""Add conversation_session_id linkage to guided_sessions (M24).

Guided sessions previously treated their own id as a conversation-session id
when talking to ConversationManager, colliding with the autoincrement PK
ConversationManager owns. This adds a real nullable FK so a guided session
can reference the conversation_sessions row that actually holds its turns.
Existing rows keep NULL; no data backfill (historical guided sessions have
no reliable linkage).

Revision ID: 0014_guided_conv_linkage
Revises: 0013_signal_supersession
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_guided_conv_linkage"
down_revision: str | Sequence[str] | None = "0013_signal_supersession"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "guided_sessions",
        sa.Column("conversation_session_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_guided_sessions_conversation_session_id",
        "guided_sessions",
        ["conversation_session_id"],
    )
    op.create_foreign_key(
        "fk_guided_sessions_conversation_session_id",
        "guided_sessions",
        "conversation_sessions",
        ["conversation_session_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_guided_sessions_conversation_session_id",
        "guided_sessions",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_guided_sessions_conversation_session_id", table_name="guided_sessions"
    )
    op.drop_column("guided_sessions", "conversation_session_id")
