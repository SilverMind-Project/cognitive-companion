from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.core.time import UTCDateTime


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    turns: Mapped[list[ConversationTurn]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("conversation_sessions.id"))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(32))  # user, assistant, rules_engine, system
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped[ConversationSession] = relationship(back_populates="turns")
