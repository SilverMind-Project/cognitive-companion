"""Transcript/event retention pruning (M29).

Leaf module: depends only on ``RuntimeContext``. The episodic-memory write
this module used to own (``write_session_observation``) moved to
``memory_bridge.py::GuidedMemoryBridge`` in DL-M05, which fires on every
terminal transition (not just ``complete()``) and also writes the activity
ledger; see that module's docstring.
"""

from __future__ import annotations

from datetime import timedelta

from backend.core.logging import get_logger
from backend.services.guided_task.context import RuntimeContext

logger = get_logger(__name__)


class Retention:
    """Transcript/event retention pruning."""

    def __init__(self, ctx: RuntimeContext) -> None:
        self._ctx = ctx

    async def prune_retained_data(self) -> dict[str, int]:
        ctx = self._ctx
        days = ctx.settings.as_int("guided_task.transcript_retention_days")
        cutoff = ctx.now() - timedelta(days=days)
        transcript_sessions = 0
        conversation_manager = ctx.conversation_manager
        if conversation_manager is not None:
            conversation_session_ids = ctx.store.list_prunable_conversation_session_ids(cutoff)
            # A conversation shared with the realtime companion may carry non-guided
            # turns too; pruning it once its linked guided session is 30+ days old
            # matches the existing global conversation TTL policy already bounding
            # reads (ConversationManager.ttl_minutes), so this is acceptable.
            transcript_sessions = conversation_manager.prune_sessions(conversation_session_ids)
        events = ctx.store.prune_events_before(cutoff)
        sessions = ctx.store.prune_sessions_before(cutoff)
        logger.info(
            "guided_retention_pruned",
            events=events,
            sessions=sessions,
            transcript_sessions=transcript_sessions,
            retention_days=days,
        )
        return {
            "events": events,
            "sessions": sessions,
            "transcript_sessions": transcript_sessions,
        }
