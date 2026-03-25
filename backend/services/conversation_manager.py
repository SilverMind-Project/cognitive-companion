"""
Manages conversation history with TTL, actor types, and DB persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.models.conversation import ConversationSession, ConversationTurn

logger = get_logger(__name__)


class ConversationManager:
    """Persists and retrieves conversation turns with configurable TTL."""

    def __init__(self, db_session_factory) -> None:
        self.db_session_factory = db_session_factory
        self.ttl_minutes = settings.get("conversation.history_ttl_minutes", 120)
        self.max_turns = settings.get("conversation.max_turns", 50)

    def create_session(self) -> int:
        """Create a new conversation session and return its ID."""
        db: Session = self.db_session_factory()
        try:
            session = ConversationSession()
            db.add(session)
            db.commit()
            db.refresh(session)
            return session.id
        finally:
            db.close()

    def end_session(self, session_id: int) -> None:
        """Mark a conversation session as ended."""
        db: Session = self.db_session_factory()
        try:
            session = db.get(ConversationSession, session_id)
            if session:
                session.ended_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    def add_turn(
        self,
        session_id: int,
        actor: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Add a conversation turn.
        actor: 'user', 'assistant', 'rules_engine', 'system'
        """
        if not content.strip():
            return

        db: Session = self.db_session_factory()
        try:
            turn = ConversationTurn(
                session_id=session_id,
                actor=actor,
                content=content.strip(),
                metadata_json=metadata,
            )
            db.add(turn)
            db.commit()
        finally:
            db.close()

    def get_history_text(self, session_id: int) -> str:
        """
        Get formatted conversation history for the current session,
        filtered by TTL, limited to max_turns.
        """
        db: Session = self.db_session_factory()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.ttl_minutes)
            turns = (
                db.query(ConversationTurn)
                .filter(
                    ConversationTurn.session_id == session_id,
                    ConversationTurn.timestamp >= cutoff,
                )
                .order_by(ConversationTurn.timestamp.desc())
                .limit(self.max_turns)
                .all()
            )
            # Reverse to chronological order
            turns.reverse()

            lines: list[str] = []
            for turn in turns:
                label = _actor_label(turn.actor)
                lines.append(f"{label}: {turn.content}")
            return "\n".join(lines)
        finally:
            db.close()

    def get_recent_turns(self, session_id: int, limit: int = 10) -> list[dict]:
        """Get recent turns as dicts for API responses."""
        db: Session = self.db_session_factory()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.ttl_minutes)
            turns = (
                db.query(ConversationTurn)
                .filter(
                    ConversationTurn.session_id == session_id,
                    ConversationTurn.timestamp >= cutoff,
                )
                .order_by(ConversationTurn.timestamp.desc())
                .limit(limit)
                .all()
            )
            turns.reverse()
            return [
                {
                    "actor": t.actor,
                    "content": t.content,
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                    "metadata": t.metadata_json,
                }
                for t in turns
            ]
        finally:
            db.close()

    def prune_old_turns(self) -> int:
        """Delete turns older than TTL. Returns count deleted."""
        db: Session = self.db_session_factory()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.ttl_minutes)
            count = (
                db.query(ConversationTurn)
                .filter(ConversationTurn.timestamp < cutoff)
                .delete()
            )
            db.commit()
            logger.info("conversation_pruned", deleted=count)
            return count
        finally:
            db.close()


def _actor_label(actor: str) -> str:
    labels = {
        "user": "User",
        "assistant": "Assistant",
        "rules_engine": "Rules Engine",
        "system": "System",
    }
    return labels.get(actor, actor.title())
