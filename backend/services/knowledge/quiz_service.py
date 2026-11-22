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
    KnowledgeDocumentImage,
    Quiz,
    QuizQuestion,
    QuizResponse,
    QuizSession,
)
from backend.services.knowledge.image_pipeline import ImagePipeline, variants_as_json
from backend.services.knowledge.layout_registry import LayoutRegistry
from backend.services.knowledge.references import (
    names_in_use,
    owned_object_names,
    rule_ids_referencing,
)

logger = get_logger(__name__)

_QUIZ_CONTENT_FIELDS: frozenset[str] = frozenset(
    {"title", "question_layout_id", "intro_voice_template", "voice_instruction"}
)


def _quiz_prefix(quiz_id: int) -> str:
    return f"quizzes/{quiz_id}/"


def _question_image_key(quiz_id: int, qid: int) -> str:
    # Keyed by question id, which never changes; an ordinal key would be shared by two
    # questions after a reorder and overwrite each other's images.
    return f"quizzes/{quiz_id}/q{qid}"


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


class QuizService:
    """Business logic for quizzes and quiz questions."""

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
        tag: str | None = None,
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
            if tag:
                stmt = stmt.where(Quiz.tags.contains([tag]))
                count_stmt = count_stmt.where(Quiz.tags.contains([tag]))
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

            content_changed = any(
                field in updates
                and updates[field] is not None
                and getattr(quiz, field) != updates[field]
                for field in _QUIZ_CONTENT_FIELDS
            )
            for key, val in updates.items():
                if val is not None and hasattr(quiz, key):
                    setattr(quiz, key, val)

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
            await self._image_pipeline.purge_prefix(_quiz_prefix(quiz_id))

    def add_question(self, quiz_id: int, question_data: dict[str, Any]) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)

            ord_val = question_data.get("ord")
            if ord_val is None:
                max_ord = db.execute(
                    select(func.coalesce(func.max(QuizQuestion.ord), -1)).where(
                        QuizQuestion.quiz_id == quiz_id
                    )
                ).scalar()
                ord_val = (max_ord if max_ord is not None else -1) + 1

            raw_choices = question_data.get("choices") or []
            choices = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in raw_choices]
            q = QuizQuestion(
                quiz_id=quiz_id,
                ord=ord_val,
                question_type=question_data["question_type"],
                question_text=question_data["question_text"],
                choices=choices,
                expected_answer=question_data.get("expected_answer", ""),
                explanation=question_data.get("explanation", ""),
            )
            db.add(q)
            if quiz.status == "approved":
                quiz.version += 1
            quiz.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(q)
            return self._question_out(q)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_question(self, quiz_id: int, qid: int, updates: dict[str, Any]) -> dict[str, Any]:
        db: Session = self._db_factory()
        try:
            q = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
            ).scalar_one_or_none()
            if q is None:
                raise NotFoundError(f"Question in quiz {quiz_id}", qid)

            for key, val in updates.items():
                if val is None:
                    continue
                if key == "choices":
                    setattr(
                        q,
                        key,
                        [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in val],
                    )
                elif hasattr(q, key):
                    setattr(q, key, val)

            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is not None:
                if quiz.status == "approved":
                    quiz.version += 1
                quiz.updated_at = datetime.now(UTC)

            db.commit()
            db.refresh(q)
            return self._question_out(q)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def delete_question(self, quiz_id: int, qid: int) -> None:
        """Delete an unanswered question and close the ordinal gap it leaves.

        Raises 409 when responses reference the question (``ON DELETE RESTRICT``): answered
        questions are history, so the caregiver edits the text or archives the quiz instead.
        Remaining questions are renumbered ``0..N-1`` in their existing order, and the
        question's own image objects are purged after commit.
        """
        db: Session = self._db_factory()
        try:
            q = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
            ).scalar_one_or_none()
            if q is None:
                raise NotFoundError(f"Question in quiz {quiz_id}", qid)
            image_slot = dict(q.image_slot or {})
            db.delete(q)
            try:
                db.flush()
            except IntegrityError as exc:
                db.rollback()
                responses = (
                    db.execute(
                        select(func.count(QuizResponse.id)).where(QuizResponse.question_id == qid)
                    ).scalar()
                    or 0
                )
                raise ConflictError(
                    f"Question {qid} has {responses} recorded response(s) and cannot be "
                    "deleted; edit its text or archive the quiz instead."
                ) from exc

            remaining = self._load_questions(db, quiz_id)
            self._renumber(db, remaining, list(range(len(remaining))))
            quiz = db.get(Quiz, quiz_id)
            if quiz is not None:
                if quiz.status == "approved":
                    quiz.version += 1
                quiz.updated_at = datetime.now(UTC)
            db.commit()
            stale = owned_object_names(image_slot, _quiz_prefix(quiz_id)) - names_in_use(
                (r.image_slot for r in remaining), _quiz_prefix(quiz_id)
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_objects(stale)
            await self._image_pipeline.purge_prefix(f"{_question_image_key(quiz_id, qid)}__")

    @staticmethod
    def _load_questions(db: Session, quiz_id: int) -> list[QuizQuestion]:
        return list(
            db.execute(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.ord.asc())
            ).scalars()
        )

    @staticmethod
    def _renumber(db: Session, questions: list[QuizQuestion], ords: list[int]) -> None:
        """Assign ``ords`` to ``questions`` without tripping ``uq_qq_quiz_ord`` midway.

        Moving every row to a unique negative ordinal first means no intermediate state can
        collide with an ordinal another row still holds.
        """
        for idx, q in enumerate(questions):
            q.ord = -(idx + 1000)
        db.flush()
        for q, ord_val in zip(questions, ords, strict=True):
            q.ord = ord_val

    def reorder_questions(self, quiz_id: int, items: list[dict[str, int]]) -> list[dict[str, Any]]:
        """Atomically reorder questions using a two-phase negative-ordinal flush."""
        db: Session = self._db_factory()
        try:
            quiz = db.execute(select(Quiz).where(Quiz.id == quiz_id)).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)

            questions_by_id: dict[int, QuizQuestion] = {}
            for idx, item in enumerate(items):
                q = db.execute(
                    select(QuizQuestion).where(
                        QuizQuestion.id == item["id"], QuizQuestion.quiz_id == quiz_id
                    )
                ).scalar_one_or_none()
                if q is not None:
                    q.ord = -(idx + 1000)
                    questions_by_id[q.id] = q

            db.flush()

            for item in items:
                q = questions_by_id.get(item["id"])
                if q is not None:
                    q.ord = item["ord"]

            db.commit()
            ordered = (
                db.execute(
                    select(QuizQuestion)
                    .where(QuizQuestion.quiz_id == quiz_id)
                    .order_by(QuizQuestion.ord.asc())
                )
                .scalars()
                .all()
            )
            return [self._question_out(q) for q in ordered]
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def set_question_image(
        self,
        quiz_id: int,
        qid: int,
        *,
        file_bytes: bytes | None,
        content_type: str | None,
        source_image_id: int | None,
        alt_text: str,
    ) -> dict[str, Any]:
        """Attach an uploaded file or an existing knowledge-document image to a question.

        Exactly one source is used (an upload wins over ``source_image_id``). Variants are
        rendered for the quiz's question layout under the question's id-keyed prefix;
        objects the previous image owned and the new one does not are purged after commit.
        A bound document image stays owned by its document and is never purged here.
        """
        if file_bytes is None and source_image_id is None:
            raise ValidationError("Provide an image file or a source_image_id")

        db: Session = self._db_factory()
        try:
            q = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
            ).scalar_one_or_none()
            if q is None:
                raise NotFoundError(f"Question in quiz {quiz_id}", qid)
            quiz = db.get(Quiz, quiz_id)
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)
            layout = self._validate_layout(quiz.question_layout_id)
            previous_slot = dict(q.image_slot or {})

            key = _question_image_key(quiz_id, qid)
            bound_source_id: int | None = None
            if file_bytes is not None:
                ctype = content_type or "image/jpeg"
                if self._image_pipeline is not None:
                    self._image_pipeline.validate_upload(ctype, file_bytes)
                ext = ctype.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"
                original_name = f"{key}__original.{ext}"
                if self._minio is not None:
                    await self._minio.async_upload_bytes(file_bytes, original_name, ctype)
            else:
                src = db.get(KnowledgeDocumentImage, source_image_id)
                if src is None:
                    raise NotFoundError("KnowledgeDocumentImage", source_image_id)
                original_name = src.minio_object_name
                bound_source_id = src.id

            variants: dict[str, Any] = {}
            if self._image_pipeline is not None and layout.image_slots:
                try:
                    rendered = await self._image_pipeline.render_variants(
                        original_object_name=original_name,
                        layout_id=layout.id,
                        slot_id=layout.image_slots[0].slot_id,
                        target_key_prefix=key,
                    )
                    variants = variants_as_json(rendered)
                except Exception:  # noqa: BLE001 - variant rendering is best-effort
                    logger.warning(
                        "quiz_question_variant_render_failed", quiz_id=quiz_id, question_id=qid
                    )

            new_slot: dict[str, Any] = {
                "source_image_id": bound_source_id,
                "original_object_name": original_name,
                "alt_text": alt_text,
                "variants": variants,
            }
            q.image_slot = new_slot
            if quiz.status == "approved":
                quiz.version += 1
            quiz.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(q)
            prefix = _quiz_prefix(quiz_id)
            siblings = [r.image_slot for r in self._load_questions(db, quiz_id) if r.id != qid]
            stale = (
                owned_object_names(previous_slot, prefix)
                - owned_object_names(new_slot, prefix)
                - names_in_use(siblings, prefix)
            )
            out = self._question_out(q)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_objects(stale)
        return out

    async def delete_question_image(self, quiz_id: int, qid: int) -> None:
        """Clear a question's image and purge the objects only that question owned."""
        db: Session = self._db_factory()
        try:
            q = db.execute(
                select(QuizQuestion).where(QuizQuestion.id == qid, QuizQuestion.quiz_id == quiz_id)
            ).scalar_one_or_none()
            if q is None:
                raise NotFoundError(f"Question in quiz {quiz_id}", qid)
            previous_slot = dict(q.image_slot or {})
            q.image_slot = {}
            quiz = db.get(Quiz, quiz_id)
            if quiz is not None:
                if quiz.status == "approved" and previous_slot:
                    quiz.version += 1
                quiz.updated_at = datetime.now(UTC)
            db.commit()
            prefix = _quiz_prefix(quiz_id)
            siblings = [r.image_slot for r in self._load_questions(db, quiz_id) if r.id != qid]
            stale = owned_object_names(previous_slot, prefix) - names_in_use(siblings, prefix)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_objects(stale)

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

    def _question_out(self, q: QuizQuestion) -> dict[str, Any]:
        return {
            "id": q.id,
            "quiz_id": q.quiz_id,
            "ord": q.ord,
            "question_type": q.question_type,
            "question_text": q.question_text,
            "choices": q.choices or [],
            "expected_answer": q.expected_answer,
            "explanation": q.explanation,
            "image_slot": self._image_slot_out(q.image_slot),
        }

    def _image_slot_out(self, image_slot: dict[str, Any] | None) -> dict[str, Any]:
        """The stored slot with a ``presigned_url`` on every variant, like info card slots."""
        if not image_slot:
            return {}
        out = dict(image_slot)
        variants: dict[str, Any] = {}
        for surface, v in (image_slot.get("variants") or {}).items():
            entry = dict(v)
            object_name = entry.get("object_name", "")
            entry["presigned_url"] = None
            if object_name and self._minio is not None:
                try:
                    entry["presigned_url"] = self._minio.generate_presigned_url(object_name)
                except Exception:  # noqa: BLE001 - optional presigned URL enrichment
                    logger.warning("quiz_question_presign_failed", object_name=object_name)
            variants[surface] = entry
        out["variants"] = variants
        return out
