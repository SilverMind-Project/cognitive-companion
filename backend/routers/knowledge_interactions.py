"""REST API for knowledge interaction review (read-only).
Thin router: parse filters, delegate to KnowledgeInteractionService.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.core.auth import require_permission
from backend.routers.dependencies import get_knowledge_interaction_service
from backend.schemas.knowledge_interactions import (
    InfoCardDeliveryOut,
    QuizSessionDetailOut,
    QuizSessionListOut,
    SeniorKnowledgeQueryOut,
    TagAnalyticsOut,
)
from backend.services.knowledge.interaction_service import KnowledgeInteractionService

router = APIRouter(prefix="/knowledge-interactions", tags=["knowledge-interactions"])


@router.get("/queries", response_model=list[SeniorKnowledgeQueryOut])
async def list_queries(
    senior_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    answered_via: str | None = Query(None),
    min_similarity: float | None = Query(None),
    max_similarity: float | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    svc: KnowledgeInteractionService = Depends(get_knowledge_interaction_service),
    _auth: None = Depends(require_permission("knowledge.interactions:read")),
) -> list[dict[str, Any]]:
    return svc.list_queries(
        senior_id=senior_id,
        answered_via=answered_via,
        date_from=date_from,
        date_to=date_to,
        min_similarity=min_similarity,
        max_similarity=max_similarity,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/quiz-sessions", response_model=list[QuizSessionListOut])
async def list_quiz_sessions(
    quiz_id: int | None = Query(None),
    senior_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    svc: KnowledgeInteractionService = Depends(get_knowledge_interaction_service),
    _auth: None = Depends(require_permission("knowledge.interactions:read")),
) -> list[dict[str, Any]]:
    return svc.list_quiz_sessions(
        quiz_id=quiz_id,
        senior_id=senior_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/quiz-sessions/{session_id}", response_model=QuizSessionDetailOut)
async def get_quiz_session_detail(
    session_id: int,
    svc: KnowledgeInteractionService = Depends(get_knowledge_interaction_service),
    _auth: None = Depends(require_permission("knowledge.interactions:read")),
) -> dict[str, Any]:
    return svc.get_quiz_session(session_id)


@router.get("/info-card-deliveries", response_model=list[InfoCardDeliveryOut])
async def list_info_card_deliveries(
    info_card_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    svc: KnowledgeInteractionService = Depends(get_knowledge_interaction_service),
    _auth: None = Depends(require_permission("knowledge.interactions:read")),
) -> list[dict[str, Any]]:
    return svc.list_info_card_deliveries(
        info_card_id=info_card_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# -- Analytics ---------------------------------------------------------------
analytics_router = APIRouter(prefix="/knowledge/analytics", tags=["knowledge-analytics"])


@analytics_router.get("/tags", response_model=TagAnalyticsOut)
async def get_tag_analytics(
    svc: KnowledgeInteractionService = Depends(get_knowledge_interaction_service),
    _auth: None = Depends(require_permission("knowledge.interactions:read")),
) -> dict[str, Any]:
    """Return per-tag document count, quiz count, and average quiz score."""
    return svc.tag_analytics()
