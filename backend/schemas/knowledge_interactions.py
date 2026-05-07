"""Pydantic v2 wire models for knowledge interaction review endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.schemas.common import OptionalUTCDatetime, UTCDatetime


# -- Senior Knowledge Query --------------------------------------------------


class SeniorKnowledgeQueryOut(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


# -- Quiz Session -------------------------------------------------------------


class QuizSessionListOut(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class QuizResponseOut(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class QuizSessionDetailOut(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


# -- Info Card Delivery -------------------------------------------------------


class InfoCardDeliveryOut(BaseModel):
    id: int
    info_card_id: int
    rule_id: int | None = None
    execution_id: int | None = None
    channels: list[str]
    delivered_at: UTCDatetime
    viewed_at: OptionalUTCDatetime = None
    dismissed_at: OptionalUTCDatetime = None
    dismissed_by: str | None = None

    model_config = ConfigDict(from_attributes=True)
