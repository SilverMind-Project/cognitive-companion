"""Read-only knowledge interaction history and per-tag analytics service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from backend.core.exceptions import NotFoundError
from backend.core.time import app_day_bounds_utc
from backend.models.knowledge import (
    InfoCardDelivery,
    KnowledgeDocument,
    Quiz,
    QuizResponse,
    QuizSession,
    SeniorKnowledgeQuery,
)


class KnowledgeInteractionService:
    """Queries senior RAG interactions, quiz sessions, card deliveries, and tag analytics."""

    def __init__(self, db_factory: Callable[[], Session]) -> None:
        self._db_factory = db_factory

    def list_queries(
        self,
        *,
        senior_id: str | None = None,
        answered_via: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        min_similarity: float | None = None,
        max_similarity: float | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """One page of senior RAG queries, newest first, as ``{items, total}``.

        ``date_from``/``date_to`` are inclusive household calendar days (``app.timezone``).
        """
        start, end = app_day_bounds_utc(date_from, date_to)
        db: Session = self._db_factory()
        try:
            stmt = select(SeniorKnowledgeQuery)
            if senior_id:
                stmt = stmt.where(SeniorKnowledgeQuery.senior_id == senior_id)
            if start is not None:
                stmt = stmt.where(SeniorKnowledgeQuery.asked_at >= start)
            if end is not None:
                stmt = stmt.where(SeniorKnowledgeQuery.asked_at < end)
            if answered_via:
                stmt = stmt.where(SeniorKnowledgeQuery.answered_via == answered_via)
            if min_similarity is not None:
                stmt = stmt.where(SeniorKnowledgeQuery.top_similarity >= min_similarity)
            if max_similarity is not None:
                stmt = stmt.where(SeniorKnowledgeQuery.top_similarity <= max_similarity)
            if q:
                stmt = stmt.where(SeniorKnowledgeQuery.query_text.ilike(f"%{q}%"))

            total = _count(db, stmt)
            rows = (
                db.execute(
                    stmt.order_by(SeniorKnowledgeQuery.asked_at.desc()).offset(offset).limit(limit)
                )
                .scalars()
                .all()
            )
            items = [
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
            return {"items": items, "total": total}
        finally:
            db.close()

    def list_quiz_sessions(
        self,
        *,
        quiz_id: int | None = None,
        senior_id: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """One page of quiz sessions, newest first, as ``{items, total}``.

        ``date_from``/``date_to`` are inclusive household calendar days (``app.timezone``).
        """
        start, end = app_day_bounds_utc(date_from, date_to)
        db: Session = self._db_factory()
        try:
            stmt = select(QuizSession)
            if quiz_id is not None:
                stmt = stmt.where(QuizSession.quiz_id == quiz_id)
            if senior_id:
                stmt = stmt.where(QuizSession.senior_id == senior_id)
            if start is not None:
                stmt = stmt.where(QuizSession.started_at >= start)
            if end is not None:
                stmt = stmt.where(QuizSession.started_at < end)
            if status:
                stmt = stmt.where(QuizSession.status == status)

            total = _count(db, stmt)
            rows = (
                db.execute(stmt.order_by(QuizSession.started_at.desc()).offset(offset).limit(limit))
                .scalars()
                .all()
            )

            session_ids = [s.id for s in rows]
            response_counts: dict[int, int] = {}
            if session_ids:
                count_rows = db.execute(
                    select(
                        QuizResponse.session_id,
                        func.count(QuizResponse.id).label("count"),
                    )
                    .where(QuizResponse.session_id.in_(session_ids))
                    .group_by(QuizResponse.session_id)
                ).all()
                response_counts = {row.session_id: row.count for row in count_rows}

            items = [
                {
                    "id": s.id,
                    "quiz_id": s.quiz_id,
                    "rule_id": s.rule_id,
                    "execution_id": s.execution_id,
                    "senior_id": s.senior_id,
                    "status": s.status,
                    "current_question_ord": s.current_question_ord,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "last_activity_at": (
                        s.last_activity_at.isoformat() if s.last_activity_at else None
                    ),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "response_count": response_counts.get(s.id, 0),
                }
                for s in rows
            ]
            return {"items": items, "total": total}
        finally:
            db.close()

    def get_quiz_session(self, session_id: int) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            session = db.execute(
                select(QuizSession).where(QuizSession.id == session_id)
            ).scalar_one_or_none()
            if session is None:
                raise NotFoundError("Quiz session", session_id)

            responses = (
                db.execute(
                    select(QuizResponse)
                    .where(QuizResponse.session_id == session_id)
                    .order_by(QuizResponse.question_ord.asc(), QuizResponse.id.asc())
                )
                .scalars()
                .all()
            )

            return {
                "id": session.id,
                "quiz_id": session.quiz_id,
                "rule_id": session.rule_id,
                "execution_id": session.execution_id,
                "senior_id": session.senior_id,
                "status": session.status,
                "current_question_ord": session.current_question_ord,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "last_activity_at": (
                    session.last_activity_at.isoformat() if session.last_activity_at else None
                ),
                "completed_at": (
                    session.completed_at.isoformat() if session.completed_at else None
                ),
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
        finally:
            db.close()

    def list_info_card_deliveries(
        self,
        *,
        info_card_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """One page of info card deliveries, newest first, as ``{items, total}``.

        ``date_from``/``date_to`` are inclusive household calendar days (``app.timezone``).
        """
        start, end = app_day_bounds_utc(date_from, date_to)
        db: Session = self._db_factory()
        try:
            stmt = select(InfoCardDelivery)
            if info_card_id is not None:
                stmt = stmt.where(InfoCardDelivery.info_card_id == info_card_id)
            if start is not None:
                stmt = stmt.where(InfoCardDelivery.delivered_at >= start)
            if end is not None:
                stmt = stmt.where(InfoCardDelivery.delivered_at < end)

            total = _count(db, stmt)
            rows = (
                db.execute(
                    stmt.order_by(InfoCardDelivery.delivered_at.desc()).offset(offset).limit(limit)
                )
                .scalars()
                .all()
            )
            items = [
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
            return {"items": items, "total": total}
        finally:
            db.close()

    def tag_analytics(self) -> dict[str, Any]:
        """Per-tag counts of active documents and quizzes, and the share of graded answers correct.

        Counts exclude archived documents and quizzes: they describe the content in use.
        The score pools every graded answer in completed sessions of any quiz carrying the
        tag, archived or not, because those answers really happened. A tag with neither
        active content nor graded answers is left out. Three grouped queries, whatever the
        number of tags.
        """
        db: Session = self._db_factory()
        try:
            doc_counts = _active_tag_counts(db, KnowledgeDocument)
            quiz_counts = _active_tag_counts(db, Quiz)

            quiz_tag = (
                select(Quiz.id.label("quiz_id"), func.unnest(Quiz.tags).label("tag"))
                .distinct()
                .subquery()
            )
            graded = (
                select(
                    quiz_tag.c.tag,
                    func.count(QuizResponse.id),
                    func.count(QuizResponse.id).filter(QuizResponse.is_correct.is_(True)),
                )
                .join(QuizSession, QuizSession.quiz_id == quiz_tag.c.quiz_id)
                .join(QuizResponse, QuizResponse.session_id == QuizSession.id)
                .where(QuizSession.status == "completed", QuizResponse.is_correct.isnot(None))
                .group_by(quiz_tag.c.tag)
            )
            scores = {
                tag: round(correct / total * 100, 1)
                for tag, total, correct in db.execute(graded)
                if total
            }

            tags = set(doc_counts) | set(quiz_counts) | set(scores)
            result = [
                {
                    "tag": tag,
                    "document_count": doc_counts.get(tag, 0),
                    "quiz_count": quiz_counts.get(tag, 0),
                    "avg_quiz_score_pct": scores.get(tag),
                }
                for tag in sorted(tags)
            ]
            result.sort(key=lambda x: x["document_count"] + x["quiz_count"], reverse=True)
            return {"tags": result}
        finally:
            db.close()


def _count(db: Session, stmt: Select[Any]) -> int:
    """Total rows matching ``stmt``'s filters, ignoring any ordering or paging."""
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


def _active_tag_counts(db: Session, model: type[KnowledgeDocument] | type[Quiz]) -> dict[str, int]:
    """Tag to number of non-archived ``model`` rows carrying it (a repeated tag counts once)."""
    row_tag = (
        select(model.id.label("row_id"), func.unnest(model.tags).label("tag"))
        .where(model.status != "archived")
        .distinct()
        .subquery()
    )
    stmt = select(row_tag.c.tag, func.count(row_tag.c.row_id)).group_by(row_tag.c.tag)
    return {str(tag): int(count) for tag, count in db.execute(stmt).all()}
