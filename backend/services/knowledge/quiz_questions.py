"""Quiz questions: CRUD, ordering, and question images.

Part of :class:`~backend.services.knowledge.quiz_service.QuizService`, split out by
responsibility; it shares that service's injected session factory, MinIO client, image
pipeline, and layout validation.
"""

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
from backend.models.knowledge import KnowledgeDocumentImage, Quiz, QuizQuestion, QuizResponse
from backend.services.knowledge.image_pipeline import ImagePipeline, variants_as_json
from backend.services.knowledge.layout_registry import LayoutSpec
from backend.services.knowledge.references import names_in_use, owned_object_names

# Logged under the quiz service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.quiz_service")


def quiz_prefix(quiz_id: int) -> str:
    """MinIO key prefix of every object a quiz owns."""
    return f"quizzes/{quiz_id}/"


def _question_image_key(quiz_id: int, qid: int) -> str:
    # Keyed by question id, which never changes; an ordinal key would be shared by two
    # questions after a reorder and overwrite each other's images.
    return f"quizzes/{quiz_id}/q{qid}"


class QuizQuestionsMixin:
    """Question operations; question images live under ``quizzes/{quiz_id}/q{question_id}__``."""

    _db_factory: Callable[[], Session]
    _minio: MinioClient | None
    _image_pipeline: ImagePipeline | None
    _validate_layout: Callable[[str], LayoutSpec]

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
            stale = owned_object_names(image_slot, quiz_prefix(quiz_id)) - names_in_use(
                (r.image_slot for r in remaining), quiz_prefix(quiz_id)
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
        """Atomically apply a complete new order (two-phase negative-ordinal flush).

        ``items`` must name every question of the quiz exactly once with ords ``0..N-1``.
        A partial list used to be accepted: unknown ids were skipped silently, and an ord
        left to an unlisted question collided on ``uq_qq_quiz_ord`` as a 500.
        """
        db: Session = self._db_factory()
        try:
            quiz = db.execute(
                select(Quiz).where(Quiz.id == quiz_id).with_for_update()
            ).scalar_one_or_none()
            if quiz is None:
                raise NotFoundError("Quiz", quiz_id)

            current = {q.id: q for q in self._load_questions(db, quiz_id)}
            ids = [item["id"] for item in items]
            ords = sorted(item["ord"] for item in items)
            if sorted(ids) != sorted(current) or ords != list(range(len(current))):
                raise ValidationError(
                    "Reorder must list every question of the quiz once, with ords 0..N-1"
                )
            ordered_items = sorted(items, key=lambda item: item["ord"])
            self._renumber(
                db,
                [current[item["id"]] for item in ordered_items],
                [item["ord"] for item in ordered_items],
            )
            # Question order is what the senior is asked, so it is a content change.
            if quiz.status == "approved":
                quiz.version += 1
            quiz.updated_at = datetime.now(UTC)
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
            prefix = quiz_prefix(quiz_id)
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
            prefix = quiz_prefix(quiz_id)
            siblings = [r.image_slot for r in self._load_questions(db, quiz_id) if r.id != qid]
            stale = owned_object_names(previous_slot, prefix) - names_in_use(siblings, prefix)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if self._image_pipeline is not None:
            await self._image_pipeline.purge_objects(stale)

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
