"""Pydantic v2 wire models for quizzes and questions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import OptionalUTCDatetime, OutSchema, UTCDatetime

# -- Quiz ---------------------------------------------------------------------


class QuizCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int | None = None
    title: str
    question_layout_id: str = "quiz_with_optional_image"
    intro_voice_template: str = ""
    voice_instruction: str = ""
    tags: list[str] = []


class QuizUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    question_layout_id: str | None = None
    intro_voice_template: str | None = None
    voice_instruction: str | None = None
    tags: list[str] | None = None


class QuizQuestionOut(OutSchema):
    id: int
    quiz_id: int
    ord: int
    question_type: str
    question_text: str
    choices: list[dict[str, Any]] = []
    expected_answer: str = ""
    explanation: str = ""
    image_slot: dict[str, Any] = {}


class QuizOut(OutSchema):
    id: int
    document_id: int | None = None
    title: str
    question_layout_id: str
    intro_voice_template: str = ""
    voice_instruction: str = ""
    tags: list[str] = []
    status: str
    version: int = 1
    approved_by: str | None = None
    approved_at: OptionalUTCDatetime = None
    created_at: UTCDatetime
    updated_at: UTCDatetime
    questions: list[QuizQuestionOut] = []


class QuizListOut(OutSchema):
    id: int
    document_id: int | None = None
    title: str
    question_layout_id: str
    tags: list[str] = []
    status: str
    version: int = 1
    approved_by: str | None = None
    created_at: UTCDatetime
    updated_at: UTCDatetime
    question_count: int = 0


class QuizListResponse(OutSchema):
    """Paginated quiz list."""

    items: list[QuizListOut] = []
    total: int


class QuizStatusOut(OutSchema):
    """Acknowledgement of a status transition (archive/restore/reorder)."""

    status: str


class QuizQuestionSuggestionOut(OutSchema):
    """One LLM-suggested question. Not persisted: the caregiver edits then creates."""

    question_type: str
    question_text: str
    choices: list[dict[str, Any]] = []
    expected_answer: str = ""
    explanation: str = ""


class QuizSuggestionOut(OutSchema):
    """LLM-suggested quiz draft."""

    title: str
    intro_voice_template: str = ""
    voice_instruction: str = ""
    questions: list[QuizQuestionSuggestionOut] = []


class VoiceInstructionSuggestionOut(OutSchema):
    voice_instruction: str


# -- Quiz Question ------------------------------------------------------------


class QuizChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    is_correct: bool = False


class QuizQuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: str = Field(..., pattern="^(multiple_choice|open_ended)$")
    question_text: str
    choices: list[QuizChoice] = []
    expected_answer: str = ""
    explanation: str = ""
    ord: int | None = None


class QuizQuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: str | None = Field(None, pattern="^(multiple_choice|open_ended)$")
    question_text: str | None = None
    choices: list[QuizChoice] | None = None
    expected_answer: str | None = None
    explanation: str | None = None
    ord: int | None = None


class QuizQuestionReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, int]]
