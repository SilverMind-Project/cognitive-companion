"""REST API for quizzes and quiz questions.
Thin router: parse, call service, serialize.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.auth import require_permission
from backend.core.database import get_db
from backend.core.exceptions import NotFoundError, ValidationError
from backend.models.knowledge import Quiz, QuizQuestion
from backend.schemas.quizzes import (
    QuizCreate,
    QuizPreviewRequest,
    QuizQuestionCreate,
    QuizQuestionReorder,
    QuizQuestionUpdate,
    QuizUpdate,
)

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


# -- CRUD --------------------------------------------------------------------


@router.post("", status_code=201)
async def create_quiz(
    body: QuizCreate,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    layout_registry = request.app.state.layout_registry
    if body.question_layout_id:
        layout = layout_registry.get_required(body.question_layout_id)
        if "quiz_question" not in layout.applies_to:
            raise ValidationError(
                f"Layout '{body.question_layout_id}' does not apply to quiz_question"
            )

    quiz = Quiz(
        document_id=body.document_id,
        title=body.title,
        question_layout_id=body.question_layout_id,
        intro_voice_template=body.intro_voice_template,
        tags=body.tags,
        status="draft",
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return _quiz_out(quiz, request.app.state.minio_client)


@router.get("")
async def list_quizzes(
    request: Request,
    status: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/quizzes")),
):
    stmt = select(Quiz)
    count_stmt = select(func.count(Quiz.id))
    if status:
        stmt = stmt.where(Quiz.status == status)
        count_stmt = count_stmt.where(Quiz.status == status)
    if tag:
        stmt = stmt.where(Quiz.tags.contains([tag]))
        count_stmt = count_stmt.where(Quiz.tags.contains([tag]))

    total = db.execute(count_stmt).scalar() or 0
    quizzes = db.execute(
        stmt.order_by(Quiz.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()

    return {
        "items": [
            {
                "id": q.id,
                "document_id": q.document_id,
                "title": q.title,
                "question_layout_id": q.question_layout_id,
                "tags": q.tags or [],
                "status": q.status,
                "version": q.version,
                "approved_by": q.approved_by,
                "created_at": q.created_at.isoformat() if q.created_at else None,
                "updated_at": q.updated_at.isoformat() if q.updated_at else None,
                "question_count": len(q.questions) if q.questions else 0,
            }
            for q in quizzes
        ],
        "total": total,
    }


@router.get("/{quiz_id}")
async def get_quiz(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("GET /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)
    return _quiz_out(quiz, request.app.state.minio_client)


@router.patch("/{quiz_id}")
async def update_quiz(
    quiz_id: int,
    body: QuizUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("PATCH /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)

    for key, val in body.model_dump(exclude_none=True).items():
        setattr(quiz, key, val)

    if body.question_layout_id:
        layout_registry = request.app.state.layout_registry
        layout = layout_registry.get_required(body.question_layout_id)
        if "quiz_question" not in layout.applies_to:
            raise ValidationError(
                f"Layout '{body.question_layout_id}' does not apply to quiz_question"
            )

    db.commit()
    db.refresh(quiz)
    return _quiz_out(quiz, request.app.state.minio_client)


# -- state transitions -------------------------------------------------------


@router.post("/{quiz_id}/approve")
async def approve_quiz(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)
    quiz.status = "approved"
    quiz.version += 1
    from datetime import UTC, datetime
    quiz.approved_at = datetime.now(UTC)
    quiz.approved_by = getattr(request.state, "auth_context", None)
    if quiz.approved_by and hasattr(quiz.approved_by, "name"):
        quiz.approved_by = quiz.approved_by.name
    db.commit()
    db.refresh(quiz)
    return _quiz_out(quiz, request.app.state.minio_client)


@router.post("/{quiz_id}/archive")
async def archive_quiz(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)
    quiz.status = "archived"
    db.commit()
    return {"status": "archived"}


@router.post("/{quiz_id}/restore")
async def restore_quiz(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)
    quiz.status = "draft"
    db.commit()
    return {"status": "restored"}


@router.delete("/{quiz_id}", status_code=204)
async def delete_quiz(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("DELETE /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)
    db.delete(quiz)
    db.commit()
    pipeline = request.app.state.image_pipeline
    await pipeline.purge_prefix(f"quizzes/{quiz_id}/")


@router.post("/{quiz_id}/preview")
async def preview_quiz(
    quiz_id: int,
    body: QuizPreviewRequest,
    request: Request,
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    return {"status": "not_implemented", "message": "Preview available in Phase 3"}


# -- questions ---------------------------------------------------------------


@router.post("/{quiz_id}/questions", status_code=201)
async def create_question(
    quiz_id: int,
    body: QuizQuestionCreate,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    if quiz is None:
        raise NotFoundError("Quiz", quiz_id)

    ord_val = body.ord
    if ord_val is None:
        max_ord = db.execute(
            select(func.coalesce(func.max(QuizQuestion.ord), -1)).where(
                QuizQuestion.quiz_id == quiz_id
            )
        ).scalar() or -1
        ord_val = max_ord + 1

    q = QuizQuestion(
        quiz_id=quiz_id,
        ord=ord_val,
        question_type=body.question_type,
        question_text=body.question_text,
        choices=[c.model_dump() for c in body.choices],
        expected_answer=body.expected_answer,
        explanation=body.explanation,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.patch("/{quiz_id}/questions/{qid}")
async def update_question(
    quiz_id: int,
    qid: int,
    body: QuizQuestionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("PATCH /api/v1/quizzes")),
):
    q = db.execute(
        select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
    ).scalar_one_or_none()
    if q is None:
        raise NotFoundError(f"Question in quiz {quiz_id}", qid)

    for key, val in body.model_dump(exclude_none=True).items():
        if key == "choices" and val is not None:
            setattr(q, key, [c.model_dump() if hasattr(c, "model_dump") else c for c in val])
        else:
            setattr(q, key, val)

    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.delete("/{quiz_id}/questions/{qid}", status_code=204)
async def delete_question(
    quiz_id: int,
    qid: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("DELETE /api/v1/quizzes")),
):
    q = db.execute(
        select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
    ).scalar_one_or_none()
    if q is None:
        raise NotFoundError(f"Question in quiz {quiz_id}", qid)
    db.delete(q)
    db.commit()


@router.post("/{quiz_id}/questions/reorder")
async def reorder_questions(
    quiz_id: int,
    body: QuizQuestionReorder,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    for item in body.items:
        q = db.execute(
            select(QuizQuestion).where(
                QuizQuestion.id == item["id"], QuizQuestion.quiz_id == quiz_id
            )
        ).scalar_one_or_none()
        if q:
            q.ord = item["ord"]
    db.commit()
    return {"status": "reordered"}


@router.post("/suggest")
async def suggest_quiz(
    request: Request,
    document_id: int | None = None,
    num_questions: int = 5,
    mix: str = "mixed",
    model_id: str | None = None,
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    """Generate a quiz draft via LLM from a knowledge document."""
    if document_id is None:
        from backend.core.exceptions import ValidationError
        raise ValidationError("document_id is required")

    content_gen = request.app.state.knowledge_content_gen
    suggestion = await content_gen.suggest_quiz(
        document_id,
        num_questions=num_questions,
        mix=mix,
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


@router.post("/voice-instruction-suggest")
async def suggest_voice_instruction(
    request: Request,
    document_id: int | None = None,
    resource_type: str = "quiz",
    model_id: str | None = None,
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    """Generate a voice instruction suggestion via LLM."""
    if document_id is None:
        from backend.core.exceptions import ValidationError
        raise ValidationError("document_id is required")

    content_gen = request.app.state.knowledge_content_gen
    text = await content_gen.suggest_voice_instruction(
        document_id, resource_type, model_id=model_id
    )
    return {"voice_instruction": text}


@router.post("/{quiz_id}/questions/{qid}/regenerate")
async def regenerate_question(
    quiz_id: int,
    qid: int,
    request: Request,
    db: Session = Depends(get_db),
    model_id: str | None = None,
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    """Regenerate a single quiz question via LLM."""
    q = db.execute(
        select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
    ).scalar_one_or_none()
    if q is None:
        raise NotFoundError(f"Question in quiz {quiz_id}", qid)

    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
    doc_id = quiz.document_id if quiz else None
    if doc_id is None:
        from backend.core.exceptions import ValidationError
        raise ValidationError("Quiz has no linked document for content generation")

    content_gen = request.app.state.knowledge_content_gen
    suggestion = await content_gen.regenerate_question(
        doc_id,
        question_type=q.question_type,
        existing_text=q.question_text,
        model_id=model_id,
    )
    return {
        "question_type": suggestion.question_type,
        "question_text": suggestion.question_text,
        "choices": suggestion.choices,
        "expected_answer": suggestion.expected_answer,
        "explanation": suggestion.explanation,
    }


@router.put("/{quiz_id}/questions/{qid}/image")
async def set_question_image(
    quiz_id: int,
    qid: int,
    request: Request,
    file: UploadFile | None = File(None),
    source_image_id: int | None = Form(None),
    alt_text: str = Form(""),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("POST /api/v1/quizzes")),
):
    q = db.execute(
        select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
    ).scalar_one_or_none()
    if q is None:
        raise NotFoundError(f"Question in quiz {quiz_id}", qid)

    minio = request.app.state.minio_client
    pipeline = request.app.state.image_pipeline
    quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()

    image_slot: dict[str, Any] = {"alt_text": alt_text}
    if source_image_id is not None:
        image_slot["source_image_id"] = source_image_id
    if file:
        data = await file.read()
        content_type = file.content_type or "image/jpeg"
        pipeline.validate_upload(content_type, data)
        ext = content_type.split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        object_name = f"quizzes/{quiz_id}/q{q.ord}__original.{ext}"
        await minio.async_upload_bytes(data, object_name, content_type)
        image_slot["original_object_name"] = object_name

        # Render variant for pwa
        if quiz and quiz.question_layout_id:
            try:
                variants = await pipeline.render_variants(
                    original_object_name=object_name,
                    layout_id=quiz.question_layout_id,
                    slot_id="question_image",
                    target_key_prefix=f"quizzes/{quiz_id}/q{q.ord}",
                )
                image_slot["variants"] = {
                    surface: {
                        "object_name": v.object_name,
                        "width": v.width,
                        "height": v.height,
                        "format": v.format,
                        "generated_at": v.generated_at,
                    }
                    for surface, v in variants.items()
                }
            except Exception:
                image_slot["variants"] = {}

    q.image_slot = image_slot
    db.commit()
    db.refresh(q)
    return _question_out(q)


@router.delete("/{quiz_id}/questions/{qid}/image", status_code=204)
async def delete_question_image(
    quiz_id: int,
    qid: int,
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_permission("DELETE /api/v1/quizzes")),
):
    q = db.execute(
        select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
    ).scalar_one_or_none()
    if q is None:
        raise NotFoundError(f"Question in quiz {quiz_id}", qid)
    q.image_slot = {}
    db.commit()


# -- serialisers ------------------------------------------------------------


def _quiz_out(quiz: Quiz, minio_client) -> dict[str, Any]:
    return {
        "id": quiz.id,
        "document_id": quiz.document_id,
        "title": quiz.title,
        "question_layout_id": quiz.question_layout_id,
        "intro_voice_template": quiz.intro_voice_template,
        "voice_instruction": quiz.voice_instruction or "",
        "tags": quiz.tags or [],
        "status": quiz.status,
        "version": quiz.version,
        "approved_by": quiz.approved_by,
        "approved_at": quiz.approved_at.isoformat() if quiz.approved_at else None,
        "created_at": quiz.created_at.isoformat() if quiz.created_at else None,
        "updated_at": quiz.updated_at.isoformat() if quiz.updated_at else None,
        "questions": [_question_out(q) for q in (quiz.questions or [])],
    }


def _question_out(q: QuizQuestion) -> dict[str, Any]:
    return {
        "id": q.id,
        "quiz_id": q.quiz_id,
        "ord": q.ord,
        "question_type": q.question_type,
        "question_text": q.question_text,
        "choices": q.choices or [],
        "expected_answer": q.expected_answer,
        "explanation": q.explanation,
        "image_slot": q.image_slot or {},
    }
