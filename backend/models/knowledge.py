"""SQLAlchemy 2.0 ORM models for the knowledge repository.

Tables:
  knowledge_documents       - caregiver-uploaded source text + metadata
  knowledge_document_images - MinIO image attachments for documents
  knowledge_document_chunks - text chunks with embeddings (Phase 2 writes these)
  info_cards                - caregiver-approved paraphrased information cards
  info_card_image_slots     - image bindings for info card layouts
  quizzes                   - caregiver-approved question sets
  quiz_questions            - individual questions within a quiz
  quiz_sessions             - one row per quiz delivery to the senior
  quiz_responses            - denormalized answer records for audit
  info_card_deliveries      - audit trail for info card views/dismissals
  senior_knowledge_queries  - senior-initiated RAG question log
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime

if TYPE_CHECKING:
    pass


class KnowledgeDocument(Base):
    """Caregiver-uploaded source text with metadata and review status."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="uploaded",
        server_default="uploaded",
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    images: Mapped[list[KnowledgeDocumentImage]] = relationship(
        "KnowledgeDocumentImage", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[KnowledgeDocumentChunk]] = relationship(
        "KnowledgeDocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded','chunked','approved','archived')",
            name="ck_knowledge_documents_status",
        ),
    )


class KnowledgeDocumentImage(Base):
    """Image attachment stored in MinIO under knowledge/<doc_id>/img-<n>.<ext>."""

    __tablename__ = "knowledge_document_images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    minio_object_name: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    ord: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    document: Mapped[KnowledgeDocument] = relationship("KnowledgeDocument", back_populates="images")


class KnowledgeDocumentChunk(Base):
    """Text chunk with embedding for vector search. Written by ingestion_service (Phase 2)."""

    __tablename__ = "knowledge_document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[object] = mapped_column(Vector(768), nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped[KnowledgeDocument] = relationship("KnowledgeDocument", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_kdc_doc_chunk"),
    )


class InfoCard(Base):
    """Caregiver-approved paraphrased information card for senior delivery."""

    __tablename__ = "info_cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    layout_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="text_only", server_default="text_only"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    voice_instruction: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    image_slots: Mapped[list[InfoCardImageSlot]] = relationship(
        "InfoCardImageSlot", back_populates="info_card", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','caregiver_review','approved','archived')",
            name="ck_info_cards_status",
        ),
    )


class InfoCardImageSlot(Base):
    """Image binding for one slot in an info card's layout."""

    __tablename__ = "info_card_image_slots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    info_card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("info_cards.id", ondelete="CASCADE"), nullable=False
    )
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_image_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_document_images.id", ondelete="SET NULL"),
        nullable=True,
    )
    original_object_name: Mapped[str] = mapped_column(Text, nullable=False)
    alt_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    variants: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    info_card: Mapped[InfoCard] = relationship("InfoCard", back_populates="image_slots")

    __table_args__ = (
        UniqueConstraint("info_card_id", "slot_index", name="uq_icis_card_slot"),
    )


class Quiz(Base):
    """Caregiver-approved question set for senior delivery via voice + buttons."""

    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    question_layout_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="quiz_with_optional_image",
        server_default="quiz_with_optional_image",
    )
    intro_voice_template: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    voice_instruction: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    questions: Mapped[list[QuizQuestion]] = relationship(
        "QuizQuestion", back_populates="quiz", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','caregiver_review','approved','archived')",
            name="ck_quizzes_status",
        ),
    )


class QuizQuestion(Base):
    """Single question within a quiz. Supports multiple_choice and open_ended types."""

    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    question_type: Mapped[str] = mapped_column(
        String(32),
        CheckConstraint("question_type IN ('multiple_choice', 'open_ended')"),
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    choices: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    expected_answer: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    explanation: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    image_slot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="questions")

    __table_args__ = (
        UniqueConstraint("quiz_id", "ord", name="uq_qq_quiz_ord"),
    )


class QuizSession(Base):
    """One quiz delivery session. Created by quiz_start step (Phase 3)."""

    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    quiz_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quizzes.id", ondelete="RESTRICT"), nullable=False
    )
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rules.id", ondelete="SET NULL"), nullable=True
    )
    execution_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True
    )
    senior_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="started",
        server_default="started",
    )
    current_question_ord: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('started','in_progress','completed','abandoned','timed_out')",
            name="ck_quiz_sessions_status",
        ),
    )


class QuizResponse(Base):
    """Denormalized answer record. Snapshot preserves audit when questions are edited."""

    __tablename__ = "quiz_responses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quiz_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quiz_questions.id", ondelete="RESTRICT"), nullable=False
    )
    question_ord: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    chosen_choice_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    chosen_choice_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_ended_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_qr_session_question"),
    )


class InfoCardDelivery(Base):
    """Audit trail: when an info card was delivered, viewed, and dismissed."""

    __tablename__ = "info_card_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    info_card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("info_cards.id", ondelete="RESTRICT"), nullable=False
    )
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rules.id", ondelete="SET NULL"), nullable=True
    )
    execution_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True
    )
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    viewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    dismissed_by: Mapped[str | None] = mapped_column(Text, nullable=True)


class SeniorKnowledgeQuery(Base):
    """Senior-initiated knowledge query. Logged for caregiver review."""

    __tablename__ = "senior_knowledge_queries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asked_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=func.now()
    )
    senior_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_document_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}"
    )
    source_chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}"
    )
    top_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    answered_via: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_senior_kq_asked_at", "asked_at", postgresql_using="btree"),
    )


# B-tree indices for timestamp-sorted queries (declared outside the model for
# tables that only need indexes, not constraints).
Index("idx_quiz_sessions_started_at", QuizSession.started_at.desc())
Index("idx_info_deliveries_at", InfoCardDelivery.delivered_at.desc())
