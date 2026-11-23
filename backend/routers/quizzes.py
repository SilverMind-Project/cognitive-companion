"""REST API for quizzes and quiz questions.
Thin router: parse, call service, serialize.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from backend.core.auth import AuthContext, actor_from_auth, has_token, require_permission
from backend.core.exceptions import NotFoundError, ValidationError
from backend.routers.dependencies import get_content_generation, get_quiz_service
from backend.schemas.knowledge import VoiceInstructionSuggestionOut
from backend.schemas.quizzes import (
    QuizCreate,
    QuizListResponse,
    QuizOut,
    QuizQuestionCreate,
    QuizQuestionOut,
    QuizQuestionReorder,
    QuizQuestionsReplace,
    QuizQuestionSuggestionOut,
    QuizQuestionUpdate,
    QuizStatusOut,
    QuizSuggestionOut,
    QuizUpdate,
)
from backend.services.knowledge.content_generation import ContentGenerationService
from backend.services.knowledge.quiz_service import QuizService

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


# -- CRUD --------------------------------------------------------------------


@router.post("", status_code=201, response_model=QuizOut)
async def create_quiz(
    body: QuizCreate,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    return svc.create_quiz(body.model_dump())


@router.get("", response_model=QuizListResponse)
async def list_quizzes(
    status: str | None = Query(None),
    tag: list[str] | None = Query(
        None, description="Matches items carrying any of these tags (repeat the parameter)."
    ),
    document_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:read")),
) -> dict[str, Any]:
    return svc.list_quizzes(
        status=status,
        tags=tag,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    quiz_id: int,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:read")),
) -> dict[str, Any]:
    return svc.get_quiz(quiz_id)


@router.patch("/{quiz_id}", response_model=QuizOut)
async def update_quiz(
    quiz_id: int,
    body: QuizUpdate,
    svc: QuizService = Depends(get_quiz_service),
    auth: AuthContext = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    """Update quiz details and, when ``questions`` is given, the whole question list atomically.

    Removing questions also needs ``quizzes:delete``, checked by the service under the quiz
    lock, as on ``PUT /{quiz_id}/questions``.
    """
    if body.questions is None:
        return svc.update_quiz(quiz_id, body.model_dump(exclude_none=True))
    return await svc.update_quiz_with_questions(
        quiz_id,
        body.model_dump(exclude_none=True, exclude={"questions"}),
        [q.model_dump(exclude_none=True) for q in body.questions],
        allow_delete=has_token(auth, "quizzes:delete"),
    )


# -- state transitions -------------------------------------------------------


@router.post("/{quiz_id}/approve", response_model=QuizOut)
async def approve_quiz(
    quiz_id: int,
    svc: QuizService = Depends(get_quiz_service),
    auth: AuthContext = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    return svc.approve_quiz(quiz_id, approved_by=actor_from_auth(auth))


@router.post("/{quiz_id}/archive", response_model=QuizStatusOut)
async def archive_quiz(
    quiz_id: int,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, str]:
    return svc.archive_quiz(quiz_id)


@router.post("/{quiz_id}/restore", response_model=QuizStatusOut)
async def restore_quiz(
    quiz_id: int,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, str]:
    return svc.restore_quiz(quiz_id)


@router.delete("/{quiz_id}", status_code=204)
async def delete_quiz(
    quiz_id: int,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:delete")),
) -> None:
    await svc.delete_quiz(quiz_id)


# -- questions ---------------------------------------------------------------


@router.post("/{quiz_id}/questions", status_code=201, response_model=QuizQuestionOut)
async def create_question(
    quiz_id: int,
    body: QuizQuestionCreate,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    return svc.add_question(quiz_id, body.model_dump())


@router.patch("/{quiz_id}/questions/{qid}", response_model=QuizQuestionOut)
async def update_question(
    quiz_id: int,
    qid: int,
    body: QuizQuestionUpdate,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    return svc.update_question(quiz_id, qid, body.model_dump(exclude_none=True))


@router.delete("/{quiz_id}/questions/{qid}", status_code=204)
async def delete_question(
    quiz_id: int,
    qid: int,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:delete")),
) -> None:
    await svc.delete_question(quiz_id, qid)


@router.post("/{quiz_id}/questions/reorder", response_model=QuizStatusOut)
async def reorder_questions(
    quiz_id: int,
    body: QuizQuestionReorder,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, str]:
    svc.reorder_questions(quiz_id, [item.model_dump() for item in body.items])
    return {"status": "reordered"}


@router.put("/{quiz_id}/questions", response_model=QuizOut)
async def replace_questions(
    quiz_id: int,
    body: QuizQuestionsReplace,
    svc: QuizService = Depends(get_quiz_service),
    auth: AuthContext = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    """Replace the quiz's ordered question list in one transaction (the quiz editor's save).

    Leaving a question out deletes it, which also needs ``quizzes:delete``: write access
    alone must not reach what the delete route guards.
    """
    return await svc.replace_questions(
        quiz_id,
        [q.model_dump(exclude_none=True) for q in body.questions],
        allow_delete=has_token(auth, "quizzes:delete"),
    )


@router.post("/suggest", response_model=QuizSuggestionOut)
async def suggest_quiz(
    document_id: int | None = None,
    num_questions: int = 5,
    mix: str = "mixed",
    model_id: str | None = None,
    content_gen: ContentGenerationService = Depends(get_content_generation),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    """Generate a quiz draft via LLM from a knowledge document."""
    if document_id is None:
        raise ValidationError("document_id is required")

    resolved_mix = cast(Literal["mc_only", "mixed"], "mc_only" if mix == "mc_only" else "mixed")
    suggestion = await content_gen.suggest_quiz(
        document_id,
        num_questions=num_questions,
        mix=resolved_mix,
        model_id=model_id,
    )
    return {
        "title": suggestion.title,
        "intro_voice_template": suggestion.intro_voice_template,
        "voice_instruction": suggestion.voice_instruction,
        "questions": [
            {
                "question_type": q.question_type,
                "question_text": q.question_text,
                "choices": q.choices,
                "expected_answer": q.expected_answer,
                "explanation": q.explanation,
            }
            for q in suggestion.questions
        ],
    }


@router.post("/voice-instruction-suggest", response_model=VoiceInstructionSuggestionOut)
async def suggest_quiz_voice_instruction(
    document_id: int | None = None,
    model_id: str | None = None,
    content_gen: ContentGenerationService = Depends(get_content_generation),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, str]:
    """Draft a quiz's voice instruction from a document. Info cards use
    ``POST /info-cards/voice-instruction-suggest`` under ``info_cards:write``."""
    if document_id is None:
        raise ValidationError("document_id is required")
    text = await content_gen.suggest_voice_instruction(document_id, "quiz", model_id=model_id)
    return {"voice_instruction": text}


@router.post("/{quiz_id}/questions/{qid}/regenerate", response_model=QuizQuestionSuggestionOut)
async def regenerate_question(
    quiz_id: int,
    qid: int,
    model_id: str | None = None,
    svc: QuizService = Depends(get_quiz_service),
    content_gen: ContentGenerationService = Depends(get_content_generation),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    """Regenerate a single quiz question via LLM."""
    quiz = svc.get_quiz(quiz_id)
    target_q = next((q for q in quiz.get("questions", []) if q["id"] == qid), None)
    if target_q is None:
        raise NotFoundError(f"Question in quiz {quiz_id}", qid)

    doc_id = quiz.get("document_id")
    if doc_id is None:
        raise ValidationError("Quiz has no linked document for content generation")

    suggestion = await content_gen.regenerate_question(
        doc_id,
        question_type=target_q["question_type"],
        existing_text=target_q["question_text"],
        model_id=model_id,
    )
    return {
        "question_type": suggestion.question_type,
        "question_text": suggestion.question_text,
        "choices": suggestion.choices,
        "expected_answer": suggestion.expected_answer,
        "explanation": suggestion.explanation,
    }


@router.put("/{quiz_id}/questions/{qid}/image", response_model=QuizQuestionOut)
async def set_question_image(
    quiz_id: int,
    qid: int,
    file: UploadFile | None = File(None),
    source_image_id: int | None = Form(None),
    alt_text: str = Form(""),
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:write")),
) -> dict[str, Any]:
    file_bytes = await file.read() if file is not None else None
    content_type = file.content_type if file is not None else None
    return await svc.set_question_image(
        quiz_id,
        qid,
        file_bytes=file_bytes,
        content_type=content_type,
        source_image_id=source_image_id,
        alt_text=alt_text,
    )


@router.delete("/{quiz_id}/questions/{qid}/image", status_code=204)
async def delete_question_image(
    quiz_id: int,
    qid: int,
    svc: QuizService = Depends(get_quiz_service),
    _auth: None = Depends(require_permission("quizzes:delete")),
) -> None:
    await svc.delete_question_image(quiz_id, qid)
