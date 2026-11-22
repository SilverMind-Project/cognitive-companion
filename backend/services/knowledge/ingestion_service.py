"""Document CRUD with status transition guards, image management, and chunk embedding.

Chunking and embedding run after the document row is committed, in their own short
transactions: the Triton call happens outside any open transaction, and the chunk rows and
the ``uploaded -> chunked`` transition are written together on a row loaded in that same
session. See ``_chunk_and_embed``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import AppError, ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.integrations.minio_client import MinioClient
from backend.integrations.triton_embedding_client import TritonEmbeddingClient
from backend.models.knowledge import (
    InfoCard,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    KnowledgeDocumentImage,
    Quiz,
)
from backend.services.knowledge.image_pipeline import ImagePipeline

logger = get_logger(__name__)

# Valid status transitions
_VALID_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"uploaded"},  # creation
    "uploaded": {"chunked", "approved", "archived"},
    "chunked": {"approved", "archived", "uploaded"},
    "approved": {"archived", "uploaded"},
    "archived": {"uploaded"},  # restore
}


class KnowledgeIngestionService:
    """Document and image management for the knowledge repository."""

    def __init__(
        self,
        db_factory,
        minio_client: MinioClient,
        image_pipeline: ImagePipeline,
        embedding_client: TritonEmbeddingClient | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._minio = minio_client
        self._image_pipeline = image_pipeline
        self._embedding_client = embedding_client

    # -- document CRUD ------------------------------------------------------

    async def create_document(
        self,
        *,
        title: str,
        source_text: str,
        tags: list[str],
        created_by: str,
        images: list[UploadFile],
    ) -> KnowledgeDocument:
        db: Session = self._db_factory()
        try:
            doc = KnowledgeDocument(
                title=title,
                source_text=source_text,
                tags=tags,
                created_by=created_by,
                status="uploaded",
            )
            db.add(doc)
            db.flush()  # get doc.id

            for idx, file in enumerate(images):
                data = await file.read()
                if not data:
                    continue
                content_type = file.content_type or "image/jpeg"
                self._image_pipeline.validate_upload(content_type, data)

                ext = _extension_for(content_type)
                object_name = f"knowledge/{doc.id}/img-{idx}.{ext}"

                # Open to get dimensions
                from io import BytesIO

                from PIL import Image

                img = Image.open(BytesIO(data))
                w, h = img.size

                await self._minio.async_upload_bytes(data, object_name, content_type)

                img_row = KnowledgeDocumentImage(
                    document_id=doc.id,
                    minio_object_name=object_name,
                    mime_type=content_type,
                    width=w,
                    height=h,
                    alt_text=file.filename or "",
                    ord=idx,
                )
                db.add(img_row)

            db.commit()
            doc_id = doc.id
            logger.info(
                "knowledge_document_created",
                doc_id=doc_id,
                image_count=len(images),
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # A failed embed leaves the document 'uploaded'; the retry job picks it up.
        await self._chunk_and_embed(doc_id)
        return self._require_document(doc_id)

    def list_documents_by_tags(
        self, tags: list[str], *, limit: int = 50
    ) -> list[KnowledgeDocument]:
        """Documents carrying every tag in ``tags`` (AND match), newest first.

        Used for DL-M05 resident-preference recall (``tags=["resident_preference",
        person_id]``): these are agent-recorded, not caregiver-authored, so
        unlike ``list_documents`` this does not filter by review ``status``.
        """
        db: Session = self._db_factory()
        try:
            stmt = (
                select(KnowledgeDocument)
                .where(KnowledgeDocument.tags.contains(tags))
                .order_by(KnowledgeDocument.created_at.desc())
                .limit(limit)
            )
            docs = list(db.execute(stmt).scalars().all())
            for doc in docs:
                _ = doc.images
                _ = doc.chunks
            return docs
        finally:
            db.close()

    def _require_document(self, doc_id: int) -> KnowledgeDocument:
        doc = self.get_document(doc_id)
        if doc is None:
            raise NotFoundError("Knowledge document", doc_id)
        return doc

    def get_document(self, doc_id: int) -> KnowledgeDocument | None:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is not None:
                _ = doc.images
                _ = doc.chunks
            return doc
        finally:
            db.close()

    def list_documents(
        self,
        *,
        status: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeDocument], int]:
        db: Session = self._db_factory()
        try:
            stmt = select(KnowledgeDocument)
            count_stmt = select(func.count(KnowledgeDocument.id))

            if status:
                stmt = stmt.where(KnowledgeDocument.status == status)
                count_stmt = count_stmt.where(KnowledgeDocument.status == status)
            if tag:
                stmt = stmt.where(KnowledgeDocument.tags.contains([tag]))
                count_stmt = count_stmt.where(KnowledgeDocument.tags.contains([tag]))
            if q:
                search = f"%{q}%"
                stmt = stmt.where(
                    (KnowledgeDocument.title.ilike(search))
                    | (KnowledgeDocument.source_text.ilike(search))
                )
                count_stmt = count_stmt.where(
                    (KnowledgeDocument.title.ilike(search))
                    | (KnowledgeDocument.source_text.ilike(search))
                )

            total = db.execute(count_stmt).scalar() or 0
            docs = (
                db.execute(
                    stmt.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(limit)
                )
                .scalars()
                .all()
            )
            for doc in docs:
                _ = doc.images
                _ = doc.chunks
            return list(docs), total
        finally:
            db.close()

    async def update_document(self, doc_id: int, **kwargs) -> KnowledgeDocument:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)

            for key, val in kwargs.items():
                if val is not None and hasattr(doc, key):
                    setattr(doc, key, val)

            source_changed = "source_text" in kwargs and kwargs["source_text"] is not None

            # If source_text changed, reset to uploaded so re-chunk happens
            if source_changed:
                doc.status = "uploaded"

            doc.updated_at = datetime.now(UTC)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        if source_changed:
            await self._chunk_and_embed(doc_id)
        return self._require_document(doc_id)

    async def reembed_document(self, doc_id: int) -> KnowledgeDocument:
        """Re-chunk and re-embed unchanged content, keeping the review status.

        The content did not change, so an approved document stays approved (and keeps
        answering senior questions); only an 'uploaded' document advances to 'chunked'.
        Raises 409 for an archived document and 503 when the embedding service is not
        configured or the embed fails, because the caregiver asked for this explicitly.
        """
        doc = self._require_document(doc_id)
        if doc.status == "archived":
            raise ConflictError(
                f"Knowledge document {doc_id} is archived; restore it before re-embedding."
            )
        if not await self._chunk_and_embed(doc_id):
            raise AppError(
                f"Re-embedding knowledge document {doc_id} failed; the embedding service is "
                "unavailable. Existing chunks were kept.",
                status_code=503,
            )
        return self._require_document(doc_id)

    # -- state transitions --------------------------------------------------

    def _transition(self, doc: KnowledgeDocument, target: str) -> KnowledgeDocument:
        current = doc.status
        allowed = _VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition document {doc.id} from '{current}' to '{target}'"
            )
        doc.status = target
        doc.updated_at = datetime.now(UTC)
        if target == "archived":
            doc.archived_at = datetime.now(UTC)
        elif target == "uploaded" and current == "archived":
            doc.archived_at = None
        return doc

    def approve_document(self, doc_id: int) -> KnowledgeDocument:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)
            self._transition(doc, "approved")
            db.commit()
            db.refresh(doc)
            logger.info("knowledge_document_approved", doc_id=doc_id)
            _ = doc.images
            _ = doc.chunks
            return doc
        except NotFoundError, ValidationError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def archive_document(self, doc_id: int) -> KnowledgeDocument:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)
            self._transition(doc, "archived")
            db.commit()
            db.refresh(doc)
            logger.info("knowledge_document_archived", doc_id=doc_id)
            _ = doc.images
            _ = doc.chunks
            return doc
        except NotFoundError, ValidationError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def restore_document(self, doc_id: int) -> KnowledgeDocument:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)
            self._transition(doc, "uploaded")
            db.commit()
            db.refresh(doc)
            logger.info("knowledge_document_restored", doc_id=doc_id)
            _ = doc.images
            _ = doc.chunks
            return doc
        except NotFoundError, ValidationError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # -- delete (hard) ------------------------------------------------------

    async def delete_document(self, doc_id: int) -> None:
        """Hard-delete a document, then purge its MinIO prefix ``knowledge/{doc_id}/``.

        Raises ConflictError (409) if any non-archived info card or quiz references
        the document. The purge runs only after the delete commits, so a failed delete
        never loses images; a failed purge leaves orphaned objects and is logged.
        """
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)

            # Block if active deliverables reference this doc
            active_cards = (
                db.execute(
                    select(func.count(InfoCard.id)).where(
                        InfoCard.document_id == doc_id,
                        InfoCard.status.in_(["draft", "caregiver_review", "approved"]),
                    )
                ).scalar()
                or 0
            )
            active_quizzes = (
                db.execute(
                    select(func.count(Quiz.id)).where(
                        Quiz.document_id == doc_id,
                        Quiz.status.in_(["draft", "caregiver_review", "approved"]),
                    )
                ).scalar()
                or 0
            )
            if active_cards > 0 or active_quizzes > 0:
                raise ConflictError(
                    f"Cannot delete document {doc_id}: "
                    f"{active_cards} active info card(s) and "
                    f"{active_quizzes} active quiz(zes) reference it"
                )

            db.delete(doc)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        prefix = f"knowledge/{doc_id}/"
        try:
            await self._image_pipeline.purge_prefix(prefix)
        except Exception:  # the delete already committed; orphaned objects are only logged
            logger.exception("knowledge_document_purge_failed", doc_id=doc_id, prefix=prefix)

    # -- chunking + embedding -----------------------------------------------

    async def _chunk_and_embed(self, doc_id: int) -> bool:
        """Replace a document's chunks with fresh embeddings. Returns True on success.

        Three steps, none holding a transaction across the Triton call: snapshot the source
        text, embed outside any transaction, then in one session lock the row, replace the
        chunks, advance 'uploaded' to 'chunked', and commit. The status change is made on the
        row loaded in that writing session; mutating an instance owned by another session is
        silently discarded and left every document 'uploaded' and re-embedded forever.

        If the text changed while embedding, the write is abandoned: the edit that changed it
        schedules its own embed, and writing the stale chunks would mark them current. Any
        failure leaves the document in its previous state for the retry job.
        """
        if self._embedding_client is None:
            logger.warning("chunk_embed_skipped_no_client", doc_id=doc_id)
            return False

        db: Session = self._db_factory()
        try:
            snapshot = db.get(KnowledgeDocument, doc_id)
            if snapshot is None or snapshot.status == "archived":
                return False
            source_text = snapshot.source_text or ""
        finally:
            db.close()

        chunks = _split_source_text(source_text)
        try:
            embeddings = await self._embedding_client.embed_chunks(chunks) if chunks else []
        except Exception:  # embedding outage: the retry job re-attempts
            logger.exception("chunk_embed_failed", doc_id=doc_id, stage="embed")
            return False
        if len(embeddings) != len(chunks):
            logger.error(
                "chunk_embed_count_mismatch",
                doc_id=doc_id,
                chunk_count=len(chunks),
                embedding_count=len(embeddings),
            )
            return False

        db = self._db_factory()
        try:
            doc_row = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id).with_for_update()
            ).scalar_one_or_none()
            if doc_row is None or doc_row.status == "archived":
                db.rollback()
                return False
            if (doc_row.source_text or "") != source_text:
                db.rollback()
                logger.info("chunk_embed_superseded", doc_id=doc_id)
                return False

            db.execute(
                delete(KnowledgeDocumentChunk).where(KnowledgeDocumentChunk.document_id == doc_id)
            )
            char_pos = 0
            for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings, strict=True)):
                db.add(
                    KnowledgeDocumentChunk(
                        document_id=doc_id,
                        chunk_index=idx,
                        text=chunk_text,
                        embedding=emb,
                        char_start=char_pos,
                        char_end=char_pos + len(chunk_text),
                    )
                )
                char_pos += len(chunk_text)

            if doc_row.status == "uploaded":
                doc_row.status = "chunked"
            doc_row.updated_at = datetime.now(UTC)
            db.commit()
        except Exception:  # previous chunks stay; the retry job re-attempts
            db.rollback()
            logger.exception("chunk_embed_failed", doc_id=doc_id, stage="write")
            return False
        finally:
            db.close()

        logger.info("chunk_embed_complete", doc_id=doc_id, chunk_count=len(chunks))
        return True

    # -- re-embed scheduler job ---------------------------------------------

    async def reembed_stuck_documents(self) -> int:
        """Retry chunk + embed for documents still in 'uploaded'. Returns the success count.

        Called periodically by the scheduler. A successful embed moves the document to
        'chunked', so each document is processed until it succeeds and then never again.
        """
        if self._embedding_client is None:
            return 0

        db: Session = self._db_factory()
        try:
            doc_ids = list(
                db.execute(
                    select(KnowledgeDocument.id)
                    .where(KnowledgeDocument.status == "uploaded")
                    .order_by(KnowledgeDocument.id.asc())
                    .limit(20)
                ).scalars()
            )
        finally:
            db.close()

        succeeded = 0
        for doc_id in doc_ids:
            if await self._chunk_and_embed(doc_id):
                succeeded += 1

        if doc_ids:
            logger.info("reembed_stuck_complete", succeeded=succeeded, attempted=len(doc_ids))
        return succeeded

    # -- images -------------------------------------------------------------

    async def add_image(
        self, doc_id: int, file: UploadFile, alt_text: str = "", ord: int | None = None
    ) -> KnowledgeDocumentImage:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)

            data = await file.read()
            if not data:
                raise ValidationError("Empty file")
            content_type = file.content_type or "image/jpeg"
            self._image_pipeline.validate_upload(content_type, data)

            ext = _extension_for(content_type)
            # Determine next ord if not provided
            if ord is None:
                max_ord = (
                    db.execute(
                        select(func.coalesce(func.max(KnowledgeDocumentImage.ord), -1)).where(
                            KnowledgeDocumentImage.document_id == doc_id
                        )
                    ).scalar()
                    or -1
                )
                ord = max_ord + 1

            object_name = f"knowledge/{doc_id}/img-{ord}.{ext}"
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(data))
            w, h = img.size
            await self._minio.async_upload_bytes(data, object_name, content_type)

            img_row = KnowledgeDocumentImage(
                document_id=doc_id,
                minio_object_name=object_name,
                mime_type=content_type,
                width=w,
                height=h,
                alt_text=alt_text or (file.filename or ""),
                ord=ord,
            )
            db.add(img_row)
            db.commit()
            db.refresh(img_row)
            return img_row
        except NotFoundError, ValidationError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_image(
        self, img_id: int, alt_text: str | None = None, ord: int | None = None
    ) -> KnowledgeDocumentImage:
        db: Session = self._db_factory()
        try:
            img_row = db.execute(
                select(KnowledgeDocumentImage).where(KnowledgeDocumentImage.id == img_id)
            ).scalar_one_or_none()
            if img_row is None:
                raise NotFoundError("Image", img_id)
            if alt_text is not None:
                img_row.alt_text = alt_text
            if ord is not None:
                img_row.ord = ord
            db.commit()
            db.refresh(img_row)
            return img_row
        except NotFoundError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def delete_image(self, img_id: int) -> None:
        db: Session = self._db_factory()
        try:
            img_row = db.execute(
                select(KnowledgeDocumentImage).where(KnowledgeDocumentImage.id == img_id)
            ).scalar_one_or_none()
            if img_row is None:
                raise NotFoundError("Image", img_id)
            object_name = img_row.minio_object_name
            db.delete(img_row)
            db.commit()
            # Purge after DB commit (per section 6.5.5 contract)
            await self._minio.async_delete_object(object_name)
        except NotFoundError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


# -- helpers ------------------------------------------------------------------


def _split_source_text(source_text: str) -> list[str]:
    """Split document text into overlapping chunks sized from ``knowledge.chunk_*_tokens``.

    Sizes are approximated at four characters per token. Whitespace-only text yields no
    chunks, which still counts as successfully chunked.
    """
    if not source_text.strip():
        return []

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.as_int("knowledge.chunk_size_tokens") * 4,
        chunk_overlap=settings.as_int("knowledge.chunk_overlap_tokens") * 4,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(source_text)


def _extension_for(content_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
    }.get(content_type, "jpg")
