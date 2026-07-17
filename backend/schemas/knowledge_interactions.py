"""Pydantic v2 wire models for knowledge interaction review endpoints."""

from __future__ import annotations

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime

# -- Senior Knowledge Query --------------------------------------------------


class SeniorKnowledgeQueryOut(OutSchema):
    id: int
    asked_at: UTCDatetime
    senior_id: str | None = None
    query_text: str
    answer_text: str = ""
    source_document_ids: list[int] = []
    source_chunk_ids: list[int] = []
    top_similarity: float | None = None
    answered_via: str
    channel: str
    latency_ms: int | None = None


# -- Quiz Session -------------------------------------------------------------


class QuizSessionListOut(OutSchema):
    id: int
    quiz_id: int
    rule_id: int | None = None
    execution_id: int | None = None
    senior_id: str | None = None
    status: str
    current_question_ord: int = 0
    started_at: UTCDatetime
    last_activity_at: UTCDatetime
    completed_at: OptionalUTCDatetime = None
    response_count: int = 0


class QuizResponseOut(OutSchema):
    id: int
    session_id: int
    question_id: int
    question_ord: int
    question_text: str
    chosen_choice_id: str | None = None
    chosen_choice_text: str | None = None
    open_ended_text: str | None = None
    is_correct: bool | None = None
    channel: str
    answered_at: UTCDatetime
    latency_ms: int | None = None


class QuizSessionDetailOut(OutSchema):
    id: int
    quiz_id: int
    rule_id: int | None = None
    execution_id: int | None = None
    senior_id: str | None = None
    status: str
    current_question_ord: int = 0
    started_at: UTCDatetime
    last_activity_at: UTCDatetime
    completed_at: OptionalUTCDatetime = None
    responses: list[QuizResponseOut] = []


# -- Info Card Delivery -------------------------------------------------------


class InfoCardDeliveryOut(OutSchema):
    id: int
    info_card_id: int
    rule_id: int | None = None
    execution_id: int | None = None
    channels: list[str]
    delivered_at: UTCDatetime
    viewed_at: OptionalUTCDatetime = None
    dismissed_at: OptionalUTCDatetime = None
    dismissed_by: str | None = None


class TagAnalyticsItem(OutSchema):
    """Usage of one tag across documents and quizzes."""

    tag: str
    document_count: int = 0
    quiz_count: int = 0
    avg_quiz_score_pct: float | None = None


class TagAnalyticsOut(OutSchema):
    tags: list[TagAnalyticsItem] = []
