"""Quiz question list: replace a quiz's whole ordered question list in one transaction.

Part of :class:`~backend.services.knowledge.quiz_service.QuizService`, split out by
responsibility; it shares that service's injected session factory and image pipeline and
the question helpers of
:class:`~backend.services.knowledge.quiz_questions.QuizQuestionsMixin`.

The quiz editor used to save with one request per created, updated, or deleted question,
so a failure partway left a half-saved quiz and the order chosen in the editor was never
stored. Here the caregiver's list is the truth: kept questions are updated, new ones
created, missing ones deleted, and every ordinal set, or nothing changes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from backend.core.logging import get_logger
from backend.models.knowledge import Quiz, QuizQuestion, QuizResponse
from backend.services.knowledge.image_pipeline import ImagePipeline
from backend.services.knowledge.quiz_questions import _question_image_key, quiz_prefix
from backend.services.knowledge.references import names_in_use, owned_object_names

# Logged under the quiz service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.quiz_service")

_EDITABLE_FIELDS = ("question_type", "question_text", "choices", "expected_answer", "explanation")


class QuizQuestionListMixin:
    """Whole-list question replacement for the quiz editor."""

    _db_factory: Callable[[], Session]
    _image_pipeline: ImagePipeline | None
    _load_questions: Callable[[Session, int], list[QuizQuestion]]
    _renumber: Callable[[Session, list[QuizQuestion], list[int]], None]
    _quiz_out: Callable[..., dict[str, Any]]

    async def replace_questions(
        self, quiz_id: int, items: list[dict[str, Any]], *, allow_delete: bool = True
    ) -> dict[str, Any]:
        """Make ``items`` (in order) the quiz's complete question list, atomically.

        An item with ``id`` updates that question (its image is kept); one without creates
        a question; a current question that is not listed is deleted. Raises 422 for an id
        that is not this quiz's or appears twice, and 409 (changing nothing) when a
        question to delete has recorded answers. Images of deleted questions are purged
        after commit. Bumps an approved quiz's version. With ``allow_delete`` false, a list
        that would remove a question is refused with 403 (checked under the quiz lock).
        """
        db: Session = self._db_factory()
        try:
            quiz = db.execute(
                select(Quiz).where(Quiz.id == quiz_id).with_for_update()
            ).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)

            current = {q.id: q for q in self._load_questions(db, quiz_id)}
            listed_ids = [item["id"] for item in items if item.get("id") is not None]
            unknown = sorted(set(listed_ids) - set(current))
            if unknown:
                raise ValidationError(f"Questions {unknown} are not in quiz {quiz_id}")
            if len(listed_ids) != len(set(listed_ids)):
                raise ValidationError("A question is listed more than once")

            removed = [q for qid, q in current.items() if qid not in set(listed_ids)]
            if removed and not allow_delete:
                raise PermissionDeniedError("Removing questions requires quizzes:delete")
            removed_slots = {q.id: dict(q.image_slot or {}) for q in removed}
            self._delete_unanswered(db, quiz_id, removed)

            # Move the kept questions out of the way before new rows take ordinals, so no
            # intermediate state collides on uq_qq_quiz_ord.
            kept = [current[qid] for qid in listed_ids]
            self._renumber(db, kept, [-(i + 1) for i in range(len(kept))])
            db.flush()

            final: list[QuizQuestion] = []
            for idx, item in enumerate(items):
                fields = {key: item[key] for key in _EDITABLE_FIELDS if key in item}
                fields["choices"] = [dict(c) for c in fields.get("choices") or []]
                if item.get("id") is not None:
                    question = current[item["id"]]
                    for key, value in fields.items():
                        setattr(question, key, value)
                else:
                    question = QuizQuestion(quiz_id=quiz_id, ord=-(len(items) + idx + 1), **fields)
                    db.add(question)
                final.append(question)
            db.flush()
            self._renumber(db, final, list(range(len(final))))

            if quiz.status == "approved":
                quiz.version += 1
            quiz.updated_at = datetime.now(UTC)
            db.commit()
            for question in final:
                db.refresh(question)
            db.refresh(quiz)
            stale: set[str] = set()
            for slot in removed_slots.values():
                stale |= owned_object_names(slot, quiz_prefix(quiz_id))
            stale -= names_in_use((q.image_slot for q in final), quiz_prefix(quiz_id))
            result = self._quiz_out(quiz, final)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_objects(stale)
            for qid in removed_slots:
                await self._image_pipeline.purge_prefix(f"{_question_image_key(quiz_id, qid)}__")
        logger.info(
            "quiz_questions_replaced",
            quiz_id=quiz_id,
            question_count=len(items),
            removed=len(removed_slots),
        )
        return result

    @staticmethod
    def _delete_unanswered(db: Session, quiz_id: int, removed: list[QuizQuestion]) -> None:
        """Delete ``removed``; 409 naming the answered ones if any has recorded responses."""
        if not removed:
            return
        for question in removed:
            db.delete(question)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            answered = (
                db.execute(
                    select(QuizResponse.question_id, func.count(QuizResponse.id))
                    .where(QuizResponse.question_id.in_([q.id for q in removed]))
                    .group_by(QuizResponse.question_id)
                )
                .tuples()
                .all()
            )
            detail = ", ".join(f"question {qid} ({n} answer(s))" for qid, n in answered)
            raise ConflictError(
                f"Cannot remove {detail} from quiz {quiz_id}: answered questions are history. "
                "Edit their text instead, or archive the quiz."
            ) from exc
