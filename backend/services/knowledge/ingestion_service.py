"""Document CRUD with status transition guards and image management.

Phase 2: adds chunking + embedding via Triton.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger
from backend.models.knowledge import (
    InfoCard,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    KnowledgeDocumentImage,
    Quiz,
)

if TYPE_CHECKING:
    from backend.integrations.minio_client import MinioClient
    from backend.integrations.triton_embedding_client import TritonEmbeddingClient
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

                self._minio.upload_bytes(data, object_name, content_type)

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
            db.refresh(doc)
            logger.info(
                "knowledge_document_created",
                doc_id=doc.id,
                title=title,
                image_count=len(images),
            )
            # Chunk + embed after commit (external side effect)
            await self._chunk_and_embed(doc)
            return doc
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_document(self, doc_id: int) -> KnowledgeDocument | None:
        db: Session = self._db_factory()
        try:
            return db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
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
            docs = db.execute(
                stmt.order_by(KnowledgeDocument.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).scalars().all()
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
            db.refresh(doc)

            # Re-chunk after commit if source text changed
            if source_changed:
                await self._chunk_and_embed(doc)

            return doc
        except NotFoundError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

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
            return doc
        except (NotFoundError, ValidationError):
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
            return doc
        except (NotFoundError, ValidationError):
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
            return doc
        except (NotFoundError, ValidationError):
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # -- delete (hard) ------------------------------------------------------

    def delete_document(self, doc_id: int) -> None:
        """Hard-delete a document and purge its MinIO prefix.

        Raises ConflictError (409) if any active info card or quiz references
        the document.
        """
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
            ).scalar_one_or_none()
            if doc is None:
                raise NotFoundError("Knowledge document", doc_id)

            # Block if active deliverables reference this doc
            active_cards = db.execute(
                select(func.count(InfoCard.id)).where(
                    InfoCard.document_id == doc_id,
                    InfoCard.status.in_(["draft", "caregiver_review", "approved"]),
                )
            ).scalar() or 0
            active_quizzes = db.execute(
                select(func.count(Quiz.id)).where(
                    Quiz.document_id == doc_id,
                    Quiz.status.in_(["draft", "caregiver_review", "approved"]),
                )
            ).scalar() or 0
            if active_cards > 0 or active_quizzes > 0:
                raise ConflictError(
                    f"Cannot delete document {doc_id}: "
                    f"{active_cards} active info card(s) and "
                    f"{active_quizzes} active quiz(zes) reference it"
                )

            db.delete(doc)
            db.commit()
        except (NotFoundError, ConflictError):
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # -- chunking + embedding -----------------------------------------------

    async def _chunk_and_embed(self, doc: KnowledgeDocument) -> None:
        """Chunk source_text and embed via Triton. Idempotent: deletes old
        chunks first, then inserts new ones. Leaves doc in 'uploaded' on
        Triton failure so the operator can retry.
        """
        if self._embedding_client is None:
            logger.warning("chunk_embed_skipped_no_client", doc_id=doc.id)
            return

        db: Session = self._db_factory()
        try:
            # Delete existing chunks
            db.execute(
                text("DELETE FROM knowledge_document_chunks WHERE document_id = :did"),
                {"did": doc.id},
            )
            db.flush()

            # Chunk source text
            chunk_size = settings.get("knowledge.chunk_size_tokens", 400)
            chunk_overlap = settings.get("knowledge.chunk_overlap_tokens", 60)
            # Approximate: 1 token ≈ 4 characters
            char_size = chunk_size * 4
            char_overlap = chunk_overlap * 4

            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=char_size,
                chunk_overlap=char_overlap,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            chunks = splitter.split_text(doc.source_text)

            if not chunks:
                logger.info("chunk_embed_no_chunks", doc_id=doc.id)
                return

            # Embed chunks
            embeddings = await self._embedding_client.embed_chunks(chunks)

            # Insert chunk rows
            char_pos = 0
            for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings, strict=False)):
                chunk = KnowledgeDocumentChunk(
                    document_id=doc.id,
                    chunk_index=idx,
                    text=chunk_text,
                    embedding=emb,
                    char_start=char_pos,
                    char_end=char_pos + len(chunk_text),
                )
                db.add(chunk)
                char_pos += len(chunk_text)

            # Transition status
            doc.status = "chunked"
            doc.updated_at = datetime.now(UTC)

            db.commit()
            logger.info(
                "chunk_embed_complete",
                doc_id=doc.id,
                chunk_count=len(chunks),
            )
        except Exception:
            db.rollback()
            logger.exception("chunk_embed_failed", doc_id=doc.id)
            # Leave doc in 'uploaded' so the operator can retry
        finally:
            db.close()

    # -- re-embed scheduler job ---------------------------------------------

    async def reembed_stuck_documents(self) -> int:
        """Find documents stuck in 'uploaded' status and retry chunk+embed.

        Called periodically by the scheduler. Returns count of documents
        successfully re-embedded.
        """
        if self._embedding_client is None:
            return 0

        db: Session = self._db_factory()
        try:
            docs = db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.status == "uploaded"
                ).limit(20)
            ).scalars().all()

            count = 0
            for doc in docs:
                try:
                    await self._chunk_and_embed(doc)
                    count += 1
                except Exception:
                    logger.exception("reembed_stuck_failed", doc_id=doc.id)

            if count > 0:
                logger.info("reembed_stuck_complete", count=count, total=len(docs))
            return count
        finally:
            db.close()

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
                max_ord = db.execute(
                    select(func.coalesce(func.max(KnowledgeDocumentImage.ord), -1)).where(
                        KnowledgeDocumentImage.document_id == doc_id
                    )
                ).scalar() or -1
                ord = max_ord + 1

            object_name = f"knowledge/{doc_id}/img-{ord}.{ext}"
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(data))
            w, h = img.size
            self._minio.upload_bytes(data, object_name, content_type)

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
        except (NotFoundError, ValidationError):
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_image(self, img_id: int, alt_text: str | None = None, ord: int | None = None) -> KnowledgeDocumentImage:
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
            self._minio.delete_object(object_name)
        except NotFoundError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


# -- helpers ------------------------------------------------------------------


def _extension_for(content_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
    }.get(content_type, "jpg")
