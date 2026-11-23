"""Quiz and question CRUD, atomic question reordering, and question image rendering."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import (
    Quiz,
    QuizQuestion,
    QuizSession,
)
from backend.services.knowledge.image_pipeline import ImagePipeline
from backend.services.knowledge.layout_registry import LayoutRegistry
from backend.services.knowledge.quiz_question_list import (
    QuizQuestionListMixin,
    apply_quiz_fields,
)
from backend.services.knowledge.quiz_questions import QuizQuestionsMixin, quiz_prefix
from backend.services.knowledge.references import (
    rule_ids_referencing,
)

logger = get_logger(__name__)


def _approval_problems(questions: list[QuizQuestion]) -> list[str]:
    """Reasons a quiz cannot be shown to the resident yet; empty when it is deliverable."""
    if not questions:
        return ["Cannot approve a quiz with 0 questions."]
    problems: list[str] = []
    for q in questions:
        label = f"Question {q.ord + 1}"
        if not (q.question_text or "").strip():
            problems.append(f"{label} has no question text.")
        if q.question_type == "multiple_choice":
            choices = q.choices or []
            if len(choices) < 2 or not any(c.get("is_correct") is True for c in choices):
                problems.append(f"{label} must have at least 2 choices and 1 correct choice.")
        elif q.question_type == "open_ended" and not (q.expected_answer or "").strip():
            problems.append(f"Open-ended {label.lower()} must have a non-empty expected answer.")
    return problems


class QuizService(QuizQuestionsMixin, QuizQuestionListMixin):
    """Business logic for quizzes; question operations live in :class:`QuizQuestionsMixin`."""

    def __init__(
        self,
        db_factory: Callable[[], Session],
        minio_client: MinioClient | None,
        image_pipeline: ImagePipeline | None,
        layout_registry: LayoutRegistry,
    ) -> None:
        self._db_factory = db_factory
        self._minio = minio_client
        self._image_pipeline = image_pipeline
        self._layouts = layout_registry

    def _validate_layout(self, layout_id: str) -> Any:
        layout = self._layouts.get(layout_id)
        if layout is None or "quiz_question" not in layout.applies_to:
            raise ValidationError(f"Layout '{layout_id}' does not apply to quiz_question")
        return layout

    def create_quiz(self, payload_dict: dict[str, Any]) -> dict[str, Any]:
        layout_id = payload_dict.get("question_layout_id") or "quiz_with_optional_image"
        self._validate_layout(layout_id)

        db: Session = self._db_factory()
        try:
            quiz = Quiz(
                document_id=payload_dict.get("document_id"),
                title=payload_dict["title"],
                question_layout_id=layout_id,
                intro_voice_template=payload_dict.get("intro_voice_template", ""),
                voice_instruction=payload_dict.get("voice_instruction", ""),
                tags=payload_dict.get("tags") or [],
                status="draft",
                version=1,
            )
            db.add(quiz)
            db.flush()

            questions_in = payload_dict.get("questions") or []
            created_questions: list[QuizQuestion] = []
            for idx, q_data in enumerate(questions_in):
                ord_val = q_data.get("ord") if q_data.get("ord") is not None else idx
                raw_choices = q_data.get("choices") or []
                choices = [
                    c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in raw_choices
                ]
                q = QuizQuestion(
                    quiz_id=quiz.id,
                    ord=ord_val,
                    question_type=q_data.get("question_type", "multiple_choice"),
                    question_text=q_data.get("question_text", ""),
                    choices=choices,
                    expected_answer=q_data.get("expected_answer", ""),
                    explanation=q_data.get("explanation", ""),
                )
                db.add(q)
                created_questions.append(q)

            db.commit()
            db.refresh(quiz)
            for q in created_questions:
                db.refresh(q)
            created_questions.sort(key=lambda item: item.ord)
            return self._quiz_out(quiz, created_questions)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_quizzes(
        self,
        *,
        status: str | None = None,
        tags: list[str] | None = None,
        document_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            stmt = select(Quiz)
            count_stmt = select(func.count(Quiz.id))
            if status:
                stmt = stmt.where(Quiz.status == status)
                count_stmt = count_stmt.where(Quiz.status == status)
            if tags:
                # Any selected tag matches (array overlap), the same as the knowledge
                # query step's tag filter.
                stmt = stmt.where(Quiz.tags.overlap(tags))
                count_stmt = count_stmt.where(Quiz.tags.overlap(tags))
            if document_id is not None:
                stmt = stmt.where(Quiz.document_id == document_id)
                count_stmt = count_stmt.where(Quiz.document_id == document_id)

            total = db.execute(count_stmt).scalar() or 0
            quizzes = (
                db.execute(stmt.order_by(Quiz.created_at.desc()).offset(offset).limit(limit))
                .scalars()
                .all()
            )

            quiz_ids = [q.id for q in quizzes]
            question_counts: dict[int, int] = {}
            if quiz_ids:
                rows = db.execute(
                    select(
                        QuizQuestion.quiz_id,
                        func.count(QuizQuestion.id).label("cnt"),
                    )
                    .where(QuizQuestion.quiz_id.in_(quiz_ids))
                    .group_by(QuizQuestion.quiz_id)
                ).all()
                question_counts = {row.quiz_id: row.cnt for row in rows}

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
                        "question_count": question_counts.get(q.id, 0),
                    }
                    for q in quizzes
                ],
                "total": total,
            }
        finally:
            db.close()

    def get_quiz(self, quiz_id: int) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)
            questions = (
                db.execute(
                    select(QuizQuestion)
                    .where(QuizQuestion.quiz_id == quiz_id)
                    .order_by(QuizQuestion.ord.asc())
                )
                .scalars()
                .all()
            )
            return self._quiz_out(quiz, list(questions))
        finally:
            db.close()

    def update_quiz(self, quiz_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        if "question_layout_id" in updates and updates["question_layout_id"] is not None:
            self._validate_layout(updates["question_layout_id"])

        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)

            content_changed = apply_quiz_fields(quiz, updates)

            if quiz.status == "approved" and content_changed:
                quiz.version += 1

            quiz.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(quiz)
            questions = (
                db.execute(
                    select(QuizQuestion)
                    .where(QuizQuestion.quiz_id == quiz_id)
                    .order_by(QuizQuestion.ord.asc())
                )
                .scalars()
                .all()
            )
            return self._quiz_out(quiz, list(questions))
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def approve_quiz(self, quiz_id: int, *, approved_by: str | None) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)
            questions = self._load_questions(db, quiz_id)
            problems = _approval_problems(questions)
            if problems:
                raise ConflictError(" ".join(problems))
            quiz.status = "approved"
            quiz.version += 1
            quiz.approved_at = datetime.now(UTC)
            quiz.approved_by = approved_by
            quiz.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(quiz)
            return self._quiz_out(quiz, questions)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def archive_quiz(self, quiz_id: int) -> dict[str, str]:
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)
            quiz.status = "archived"
            quiz.updated_at = datetime.now(UTC)
            db.commit()
            return {"status": "archived"}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def restore_quiz(self, quiz_id: int) -> dict[str, str]:
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)
            quiz.status = "draft"
            quiz.updated_at = datetime.now(UTC)
            db.commit()
            return {"status": "restored"}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def delete_quiz(self, quiz_id: int) -> None:
        """Hard-delete a quiz that no rule uses and that was never played.

        Raises 409 when any rule step (enabled or disabled) references the quiz, or when
        session history exists (protected by ``ON DELETE RESTRICT``); archive such a quiz
        instead. MinIO objects are purged only after commit.
        """
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)
            rule_ids = rule_ids_referencing(
                db, step_type="quiz_start", config_key="quiz_id", resource_id=quiz_id
            )
            if rule_ids:
                raise ConflictError(
                    f"Quiz {quiz_id} is used by rule(s) {rule_ids}; remove it from those "
                    "rules or archive the quiz instead."
                )
            db.delete(quiz)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                sessions = (
                    db.execute(
                        select(func.count(QuizSession.id)).where(QuizSession.quiz_id == quiz_id)
                    ).scalar()
                    or 0
                )
                raise ConflictError(
                    f"Quiz {quiz_id} has {sessions} session record(s) and cannot be deleted; "
                    "archive it instead."
                ) from exc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_prefix(quiz_prefix(quiz_id))

    def _quiz_out(self, quiz: Quiz, questions: list[QuizQuestion] | None = None) -> dict[str, Any]:
        resolved_questions = (
            questions
            if questions is not None
            else sorted(quiz.questions or [], key=lambda item: item.ord)
        )
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
            "questions": [self._question_out(q) for q in resolved_questions],
        }
