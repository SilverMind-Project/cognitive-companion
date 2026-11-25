"""Image attachments on knowledge documents.

Part of :class:`~backend.services.knowledge.ingestion_service.KnowledgeIngestionService`,
split out by responsibility; it shares that service's injected session factory, MinIO
client, and image pipeline.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.exceptions import NotFoundError, ValidationError
from backend.integrations.minio_client import MinioClient
from backend.models.knowledge import KnowledgeDocument, KnowledgeDocumentImage
from backend.services.knowledge.image_pipeline import ImagePipeline


class DocumentImagesMixin:
    """Add, edit, and delete a document's images; objects live under ``knowledge/{doc_id}/``."""

    _db_factory: Callable[[], Session]
    _minio: MinioClient
    _image_pipeline: ImagePipeline

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

            ext = image_extension(content_type)
            # Determine next ord if not provided
            if ord is None:
                max_ord = db.execute(
                    select(func.coalesce(func.max(KnowledgeDocumentImage.ord), -1)).where(
                        KnowledgeDocumentImage.document_id == doc_id
                    )
                ).scalar()
                ord = (max_ord if max_ord is not None else -1) + 1

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
        self,
        img_id: int,
        alt_text: str | None = None,
        ord: int | None = None,
        *,
        doc_id: int | None = None,
    ) -> KnowledgeDocumentImage:
        db: Session = self._db_factory()
        try:
            stmt = select(KnowledgeDocumentImage).where(KnowledgeDocumentImage.id == img_id)
            if doc_id is not None:
                stmt = stmt.where(KnowledgeDocumentImage.document_id == doc_id)
            img_row = db.execute(stmt).scalar_one_or_none()
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

    async def delete_image(self, img_id: int, *, doc_id: int | None = None) -> None:
        db: Session = self._db_factory()
        try:
            stmt = select(KnowledgeDocumentImage).where(KnowledgeDocumentImage.id == img_id)
            if doc_id is not None:
                stmt = stmt.where(KnowledgeDocumentImage.document_id == doc_id)
            img_row = db.execute(stmt).scalar_one_or_none()
            if img_row is None:
                raise NotFoundError("Image", img_id)
            object_name = img_row.minio_object_name
            db.delete(img_row)
            db.commit()
            # Purge after DB commit so the DB state is authoritative even if MinIO fails.
            await self._minio.async_delete_object(object_name)
        except NotFoundError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def image_extension(content_type: str) -> str:
    """File extension for an allowed image MIME type (``jpg`` when unknown)."""
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
    }.get(content_type, "jpg")
