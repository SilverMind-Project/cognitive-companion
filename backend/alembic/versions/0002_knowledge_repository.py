"""Knowledge repository

Revision ID: 0002_knowledge_repository
Revises: 68d9e37c65c2
Create Date: 2026-05-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import NullType

import backend.core.time
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002_knowledge_repository'
down_revision: str | Sequence[str] | None = '68d9e37c65c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create knowledge repository tables and indices."""
    # pgvector + pgvectorscale extensions (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS vectorscale CASCADE")

    # -- knowledge_documents -------------------------------------------------
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="uploaded",
            nullable=False,
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded','chunked','approved','archived')",
            name="ck_knowledge_documents_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- knowledge_document_images -------------------------------------------
    op.create_table(
        "knowledge_document_images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("minio_object_name", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("alt_text", sa.Text(), server_default="", nullable=False),
        sa.Column("ord", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- knowledge_document_chunks (embedding column for Phase 2) ------------
    op.create_table(
        "knowledge_document_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", NullType(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_kdc_doc_chunk"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- info_cards ----------------------------------------------------------
    op.create_table(
        "info_cards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("layout_id", sa.Text(), server_default="text_only", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','caregiver_review','approved','archived')",
            name="ck_info_cards_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- info_card_image_slots -----------------------------------------------
    op.create_table(
        "info_card_image_slots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "info_card_id",
            sa.BigInteger(),
            sa.ForeignKey("info_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column(
            "source_image_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_document_images.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_object_name", sa.Text(), nullable=False),
        sa.Column("alt_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "variants",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.UniqueConstraint("info_card_id", "slot_index", name="uq_icis_card_slot"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quizzes -------------------------------------------------------------
    op.create_table(
        "quizzes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "question_layout_id",
            sa.Text(),
            server_default="quiz_with_optional_image",
            nullable=False,
        ),
        sa.Column(
            "intro_voice_template",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=True),
        sa.Column("approved_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column(
            "created_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','caregiver_review','approved','archived')",
            name="ck_quizzes_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quiz_questions ------------------------------------------------------
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "quiz_id",
            sa.BigInteger(),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column(
            "choices",
            JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "expected_answer",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "explanation",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "image_slot",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "question_type IN ('multiple_choice', 'open_ended')",
            name="ck_quiz_questions_type",
        ),
        sa.UniqueConstraint("quiz_id", "ord", name="uq_qq_quiz_ord"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quiz_sessions -------------------------------------------------------
    op.create_table(
        "quiz_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "quiz_id",
            sa.BigInteger(),
            sa.ForeignKey("quizzes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            sa.ForeignKey("rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execution_id",
            sa.BigInteger(),
            sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("senior_id", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            server_default="started",
            nullable=False,
        ),
        sa.Column(
            "current_question_ord",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('started','in_progress','completed','abandoned','timed_out')",
            name="ck_quiz_sessions_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- quiz_responses ------------------------------------------------------
    op.create_table(
        "quiz_responses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("quiz_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.BigInteger(),
            sa.ForeignKey("quiz_questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("question_ord", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("chosen_choice_id", sa.Text(), nullable=True),
        sa.Column("chosen_choice_text", sa.Text(), nullable=True),
        sa.Column("open_ended_text", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column(
            "answered_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.UniqueConstraint("session_id", "question_id", name="uq_qr_session_question"),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- info_card_deliveries ------------------------------------------------
    op.create_table(
        "info_card_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "info_card_id",
            sa.BigInteger(),
            sa.ForeignKey("info_cards.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            sa.ForeignKey("rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execution_id",
            sa.BigInteger(),
            sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channels", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "delivered_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("viewed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("dismissed_at", backend.core.time.UTCDateTime(), nullable=True),
        sa.Column("dismissed_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- senior_knowledge_queries --------------------------------------------
    op.create_table(
        "senior_knowledge_queries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "asked_at",
            backend.core.time.UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("senior_id", sa.Text(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column(
            "answer_text",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "source_document_ids",
            sa.ARRAY(sa.Integer()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "source_chunk_ids",
            sa.ARRAY(sa.Integer()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("top_similarity", sa.Float(), nullable=True),
        sa.Column("answered_via", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- indices -------------------------------------------------------------
    op.create_index(
        "idx_senior_kq_asked_at",
        "senior_knowledge_queries",
        ["asked_at"],
        unique=False,
    )
    op.create_index(
        "idx_quiz_sessions_started_at",
        "quiz_sessions",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        "idx_info_deliveries_at",
        "info_card_deliveries",
        ["delivered_at"],
        unique=False,
    )

    # -- eink info_card template row -----------------------------------------
    op.execute(
        sa.text(
            """INSERT INTO image_templates (name, description, width, height, image_filename, font_filename, regions_json, is_default)
               VALUES (
                   'info_card',
                   'Info card display (title + image + body)',
                   800, 480,
                   'info_card_bg.png',
                   'NotoSansTamil-Regular.ttf',
                   :regions,
                   false
               )"""
        ).bindparams(
            sa.bindparam(
                "regions",
                value=[
                    {
                        "name": "title",
                        "x": 20,
                        "y": 10,
                        "width": 760,
                        "height": 50,
                        "font_size_max": 28,
                        "font_size_min": 14,
                        "align": "center",
                        "bg_color": [0, 0, 0, 160],
                        "text_color": [255, 255, 255, 255],
                        "multiline": True,
                    },
                    {
                        "name": "image",
                        "x": 20,
                        "y": 70,
                        "width": 760,
                        "height": 260,
                        "type": "image",
                    },
                    {
                        "name": "body",
                        "x": 20,
                        "y": 340,
                        "width": 760,
                        "height": 130,
                        "font_size_max": 18,
                        "font_size_min": 10,
                        "align": "left",
                        "bg_color": [0, 0, 0, 0],
                        "text_color": [0, 0, 0, 255],
                        "multiline": True,
                    },
                ],
                type_=JSONB(),
            )
        )
    )


def downgrade() -> None:
    """Remove knowledge repository tables and indices."""
    # Delete the info_card template row
    op.execute("DELETE FROM image_templates WHERE name = 'info_card'")

    # Indices
    op.drop_index("idx_info_deliveries_at", table_name="info_card_deliveries")
    op.drop_index("idx_quiz_sessions_started_at", table_name="quiz_sessions")
    op.drop_index("idx_senior_kq_asked_at", table_name="senior_knowledge_queries")

    # Tables (reverse FK order)
    op.drop_table("senior_knowledge_queries")
    op.drop_table("info_card_deliveries")
    op.drop_table("quiz_responses")
    op.drop_table("quiz_sessions")
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
    op.drop_table("info_card_image_slots")
    op.drop_table("info_cards")
    op.drop_table("knowledge_document_chunks")
    op.drop_table("knowledge_document_images")
    op.drop_table("knowledge_documents")

    # Extensions (leave them; they may be shared)
