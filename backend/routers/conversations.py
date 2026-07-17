"""
Conversation history API router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from backend.core.auth import AuthContext, require_permission
from backend.core.logging import get_logger
from backend.schemas.misc_responses import RecentTurnsOut
from backend.services.conversation_manager import ConversationManager

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/recent", response_model=RecentTurnsOut)
async def get_recent_turns(
    request: Request,
    session_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("caregiver")),
):
    """Get recent conversation turns."""
    conv_manager: ConversationManager | None = request.app.state.conversation_manager
    if conv_manager is None:
        return {"turns": []}

    if session_id is None:
        return {"turns": [], "message": "Provide a session_id"}

    turns = conv_manager.get_recent_turns(session_id, limit=limit)
    return {"session_id": session_id, "turns": turns}
