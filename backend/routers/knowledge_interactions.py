"""REST API for knowledge interaction review (read-only).
Thin router: parse filters, query DB, serialize.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError
from backend.models.knowledge import (
    InfoCardDelivery,
    QuizResponse,
    QuizSession,
    SeniorKnowledgeQuery,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/knowledge-interactions", tags=["knowledge-interactions"])


@router.get("/queries")
async def list_queries(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    answered_via: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/knowledge-interactions")),
):
    stmt = select(SeniorKnowledgeQuery)
    if date_from:
        stmt = stmt.where(SeniorKnowledgeQuery.asked_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(SeniorKnowledgeQuery.asked_at < datetime.combine(date_to, datetime.max.time()))
    if answered_via:
        stmt = stmt.where(SeniorKnowledgeQuery.answered_via == answered_via)
    if q:
        stmt = stmt.where(SeniorKnowledgeQuery.query_text.ilike(f"%{q}%"))

    rows = db.execute(
        stmt.order_by(SeniorKnowledgeQuery.asked_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "asked_at": r.asked_at.isoformat() if r.asked_at else None,
            "senior_id": r.senior_id,
            "query_text": r.query_text,
            "answer_text": r.answer_text,
            "source_document_ids": r.source_document_ids or [],
            "source_chunk_ids": r.source_chunk_ids or [],
            "top_similarity": r.top_similarity,
            "answered_via": r.answered_via,
            "channel": r.channel,
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]


@router.get("/quiz-sessions")
async def list_quiz_sessions(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/knowledge-interactions")),
):
    stmt = select(QuizSession)
    if date_from:
        stmt = stmt.where(QuizSession.started_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(QuizSession.started_at < datetime.combine(date_to, datetime.max.time()))
    if status:
        stmt = stmt.where(QuizSession.status == status)

    rows = db.execute(
        stmt.order_by(QuizSession.started_at.desc()).limit(limit)
    ).scalars().all()

    return [
        {
            "id": s.id,
            "quiz_id": s.quiz_id,
            "rule_id": s.rule_id,
            "execution_id": s.execution_id,
            "senior_id": s.senior_id,
            "status": s.status,
            "current_question_ord": s.current_question_ord,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "last_activity_at": s.last_activity_at.isoformat() if s.last_activity_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "response_count": 0,  # populated in Phase 3
        }
        for s in rows
    ]


@router.get("/quiz-sessions/{session_id}")
async def get_quiz_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/knowledge-interactions")),
):
    session = db.execute(
        select(QuizSession).where(QuizSession.id == session_id)
    ).scalar_one_or_none()
    if session is None:
        raise NotFoundError(f"Quiz session {session_id} not found")

    responses = db.execute(
        select(QuizResponse).where(QuizResponse.session_id == session_id)
    ).scalars().all()

    return {
        "id": session.id,
        "quiz_id": session.quiz_id,
        "rule_id": session.rule_id,
        "execution_id": session.execution_id,
        "senior_id": session.senior_id,
        "status": session.status,
        "current_question_ord": session.current_question_ord,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "last_activity_at": session.last_activity_at.isoformat() if session.last_activity_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "responses": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "question_id": r.question_id,
                "question_ord": r.question_ord,
                "question_text": r.question_text,
                "chosen_choice_id": r.chosen_choice_id,
                "chosen_choice_text": r.chosen_choice_text,
                "open_ended_text": r.open_ended_text,
                "is_correct": r.is_correct,
                "channel": r.channel,
                "answered_at": r.answered_at.isoformat() if r.answered_at else None,
                "latency_ms": r.latency_ms,
            }
            for r in responses
        ],
    }


@router.get("/info-card-deliveries")
async def list_info_card_deliveries(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/knowledge-interactions")),
):
    stmt = select(InfoCardDelivery)
    if date_from:
        stmt = stmt.where(InfoCardDelivery.delivered_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(InfoCardDelivery.delivered_at < datetime.combine(date_to, datetime.max.time()))

    rows = db.execute(
        stmt.order_by(InfoCardDelivery.delivered_at.desc()).limit(limit)
    ).scalars().all()

    return [
        {
            "id": d.id,
            "info_card_id": d.info_card_id,
            "rule_id": d.rule_id,
            "execution_id": d.execution_id,
            "channels": d.channels or [],
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "viewed_at": d.viewed_at.isoformat() if d.viewed_at else None,
            "dismissed_at": d.dismissed_at.isoformat() if d.dismissed_at else None,
            "dismissed_by": d.dismissed_by,
        }
        for d in rows
    ]


# -- Analytics ---------------------------------------------------------------
analytics_router = APIRouter(prefix="/knowledge/analytics", tags=["knowledge-analytics"])


@analytics_router.get("/tags")
async def get_tag_analytics(
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/knowledge-interactions")),
):
    """Return per-tag document count, quiz count, and average quiz score."""
    from backend.models.knowledge import KnowledgeDocument, Quiz, QuizResponse, QuizSession
    from sqlalchemy import case

    # Get all distinct tags across documents and quizzes
    doc_tags = set()
    docs = db.execute(select(KnowledgeDocument.tags)).scalars().all()
    for tag_list in docs:
        for t in (tag_list or []):
            doc_tags.add(t)

    quiz_tags = set()
    quizzes = db.execute(select(Quiz.tags)).scalars().all()
    for tag_list in quizzes:
        for t in (tag_list or []):
            quiz_tags.add(t)

    all_tags = sorted(doc_tags | quiz_tags)

    result = []
    for tag in all_tags:
        doc_count = db.execute(
            select(func.count(KnowledgeDocument.id)).where(
                KnowledgeDocument.tags.any(tag)
            )
        ).scalar() or 0

        quiz_count = db.execute(
            select(func.count(Quiz.id)).where(Quiz.tags.any(tag))
        ).scalar() or 0

        # Avg quiz score: find sessions for quizzes with this tag
        quiz_ids = db.execute(
            select(Quiz.id).where(Quiz.tags.any(tag))
        ).scalars().all()

        avg_score = None
        if quiz_ids:
            session_ids = db.execute(
                select(QuizSession.id).where(
                    QuizSession.quiz_id.in_(quiz_ids),
                    QuizSession.status == "completed",
                )
            ).scalars().all()
            if session_ids:
                responses = db.execute(
                    select(QuizResponse.is_correct).where(
                        QuizResponse.session_id.in_(session_ids),
                        QuizResponse.is_correct.isnot(None),
                    )
                ).scalars().all()
                if responses:
                    avg_score = round(
                        sum(1 for r in responses if r) / len(responses) * 100, 1
                    )

        result.append({
            "tag": tag,
            "document_count": doc_count,
            "quiz_count": quiz_count,
            "avg_quiz_score_pct": avg_score,
        })

    return {"tags": sorted(result, key=lambda x: x["document_count"] + x["quiz_count"], reverse=True)}
