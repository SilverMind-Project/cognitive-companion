"""
Manages conversation history with TTL, actor types, and DB persistence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.config import settings
from backend.core.database import transaction
from backend.core.logging import get_logger
from backend.models.conversation import ConversationSession, ConversationTurn

logger = get_logger(__name__)

ALLOWED_ACTORS = frozenset(
    {"user", "assistant", "orchestrator", "rules_engine", "system", "caregiver"}
)


class ConversationManager:
    """Persists and retrieves conversation turns with configurable TTL."""

    def __init__(self, db_session_factory) -> None:
        self.db_session_factory = db_session_factory
        self.ttl_minutes = settings.as_int("conversation.history_ttl_minutes")
        self.max_turns = settings.as_int("conversation.max_turns")

    def create_session(self) -> int:
        """Create a new conversation session and return its ID."""
        with transaction(self.db_session_factory) as db:
            session = ConversationSession()
            db.add(session)
            db.flush()  # populate session.id before returning
            return session.id

    def end_session(self, session_id: int) -> None:
        """Mark a conversation session as ended."""
        with transaction(self.db_session_factory) as db:
            session = db.get(ConversationSession, session_id)
            if session:
                session.ended_at = datetime.now(UTC)

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

        with transaction(self.db_session_factory) as db:
            turn = ConversationTurn(
                session_id=session_id,
                actor=actor,
                content=content.strip(),
                metadata_json=metadata,
            )
            db.add(turn)

    def get_history_text(self, session_id: int) -> str:
        """
        Get formatted conversation history for the current session,
        filtered by TTL, limited to max_turns.
        """
        with transaction(self.db_session_factory) as db:
            cutoff = datetime.now(UTC) - timedelta(minutes=self.ttl_minutes)
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

    def get_recent_turns(self, session_id: int, limit: int = 10) -> list[dict]:
        """Get recent turns as dicts for API responses."""
        with transaction(self.db_session_factory) as db:
            cutoff = datetime.now(UTC) - timedelta(minutes=self.ttl_minutes)
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

    def prune_old_turns(self) -> int:
        """Delete turns older than TTL. Returns count deleted."""
        with transaction(self.db_session_factory) as db:
            cutoff = datetime.now(UTC) - timedelta(minutes=self.ttl_minutes)
            count = db.query(ConversationTurn).filter(ConversationTurn.timestamp < cutoff).delete()
            logger.info("conversation_pruned", deleted=count)
            return count

    def prune_sessions(self, session_ids: list[int]) -> int:
        """Delete externally-owned conversation sessions by ID."""
        if not session_ids:
            return 0
        with transaction(self.db_session_factory) as db:
            db.query(ConversationTurn).filter(ConversationTurn.session_id.in_(session_ids)).delete(
                synchronize_session=False
            )
            count = (
                db.query(ConversationSession)
                .filter(ConversationSession.id.in_(session_ids))
                .delete(synchronize_session=False)
            )
            logger.info("conversation_sessions_pruned", deleted=count)
            return count


def _actor_label(actor: str) -> str:
    labels = {
        "user": "User",
        "assistant": "Assistant",
        "orchestrator": "Orchestrator",
        "rules_engine": "Rules Engine",
        "system": "System",
        "caregiver": "Caregiver",
    }
    return labels.get(actor, actor.title())
