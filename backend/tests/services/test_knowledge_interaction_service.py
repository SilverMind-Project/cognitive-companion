"""Service-layer tests for KnowledgeInteractionService."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.models.knowledge import (
    InfoCard,
    InfoCardDelivery,
    KnowledgeDocument,
    Quiz,
    QuizQuestion,
    QuizResponse,
    QuizSession,
    SeniorKnowledgeQuery,
)
from backend.services.knowledge.interaction_service import KnowledgeInteractionService


@pytest.fixture
def interaction_service(db_factory) -> KnowledgeInteractionService:
    return KnowledgeInteractionService(db_factory=db_factory)


def test_list_queries_and_quiz_sessions_and_deliveries(
    db_session, interaction_service: KnowledgeInteractionService
) -> None:
    now = datetime(2026, 11, 22, 14, 0, tzinfo=UTC)
    query_row = SeniorKnowledgeQuery(
        asked_at=now,
        senior_id="senior-1",
        query_text="When does Priya visit?",
        answer_text="Priya visits on Sunday.",
        source_document_ids=[1],
        source_chunk_ids=[10],
        top_similarity=0.91,
        answered_via="rag",
        channel="voice",
        latency_ms=420,
    )
    card = InfoCard(
        title="Sunday Visit",
        body_text="Priya visits at 2pm.",
        layout_id="text_only",
        status="approved",
    )
    quiz = Quiz(
        title="Family Quiz",
        question_layout_id="quiz_with_optional_image",
        status="approved",
        tags=["family"],
    )
    db_session.add_all([query_row, card, quiz])
    db_session.flush()

    question = QuizQuestion(
        quiz_id=quiz.id,
        ord=0,
        question_type="multiple_choice",
        question_text="When does Priya visit?",
        choices=[{"id": "a", "text": "Sunday", "is_correct": True}],
    )
    db_session.add(question)
    db_session.flush()

    session = QuizSession(
        quiz_id=quiz.id,
        senior_id="senior-1",
        status="completed",
        current_question_ord=1,
        started_at=now,
        last_activity_at=now,
        completed_at=now,
    )
    db_session.add(session)
    db_session.flush()

    response = QuizResponse(
        session_id=session.id,
        question_id=question.id,
        question_ord=0,
        question_text=question.question_text,
        chosen_choice_id="a",
        chosen_choice_text="Sunday",
        is_correct=True,
        channel="voice",
        answered_at=now,
        latency_ms=1500,
    )
    delivery = InfoCardDelivery(
        info_card_id=card.id,
        channels=["pwa_popup"],
        delivered_at=now,
    )
    db_session.add_all([response, delivery])
    db_session.commit()

    queries = interaction_service.list_queries(
        senior_id="senior-1", answered_via="rag", date_from=now.date(), date_to=now.date()
    )
    assert len(queries) == 1
    assert queries[0]["query_text"] == "When does Priya visit?"

    sessions = interaction_service.list_quiz_sessions(
        quiz_id=quiz.id, senior_id="senior-1", status="completed"
    )
    assert len(sessions) == 1
    assert sessions[0]["response_count"] == 1

    detail = interaction_service.get_quiz_session(session.id)
    assert detail["id"] == session.id
    assert len(detail["responses"]) == 1
    assert detail["responses"][0]["chosen_choice_text"] == "Sunday"

    deliveries = interaction_service.list_info_card_deliveries(info_card_id=card.id)
    assert len(deliveries) == 1
    assert deliveries[0]["info_card_id"] == card.id


def test_tag_analytics_aggregates_documents_quizzes_and_scores(
    db_session, interaction_service: KnowledgeInteractionService
) -> None:
    doc = KnowledgeDocument(
        title="Family Bio",
        source_text="Priya lives in Boston.",
        tags=["family", "boston"],
        status="approved",
        created_by="caregiver",
    )
    quiz = Quiz(
        title="Family Quiz",
        question_layout_id="quiz_with_optional_image",
        tags=["family"],
        status="approved",
    )
    db_session.add_all([doc, quiz])
    db_session.flush()

    q1 = QuizQuestion(
        quiz_id=quiz.id,
        ord=0,
        question_type="open_ended",
        question_text="Q1",
        expected_answer="A1",
    )
    q2 = QuizQuestion(
        quiz_id=quiz.id,
        ord=1,
        question_type="open_ended",
        question_text="Q2",
        expected_answer="A2",
    )
    db_session.add_all([q1, q2])
    db_session.flush()

    sess = QuizSession(
        quiz_id=quiz.id,
        senior_id="senior-1",
        status="completed",
    )
    db_session.add(sess)
    db_session.flush()

    db_session.add_all(
        [
            QuizResponse(
                session_id=sess.id,
                question_id=q1.id,
                question_ord=0,
                question_text="Q1",
                is_correct=True,
                channel="voice",
            ),
            QuizResponse(
                session_id=sess.id,
                question_id=q2.id,
                question_ord=1,
                question_text="Q2",
                is_correct=False,
                channel="voice",
            ),
        ]
    )
    db_session.commit()

    analytics = interaction_service.tag_analytics()
    by_tag = {item["tag"]: item for item in analytics["tags"]}
    assert by_tag["family"]["document_count"] == 1
    assert by_tag["family"]["quiz_count"] == 1
    assert by_tag["family"]["avg_quiz_score_pct"] == 50.0
    assert by_tag["boston"]["document_count"] == 1
    assert by_tag["boston"]["quiz_count"] == 0
    assert by_tag["boston"]["avg_quiz_score_pct"] is None
