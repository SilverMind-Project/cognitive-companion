"""Chunk + embed for knowledge documents, and the retry job for documents missing chunks.

Part of :class:`~backend.services.knowledge.ingestion_service.KnowledgeIngestionService`,
split out by responsibility; it shares that service's injected session factory and
embedding client.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.triton_embedding_client import TritonEmbeddingClient
from backend.models.knowledge import KnowledgeDocument, KnowledgeDocumentChunk

# Logged under the ingestion service's logger so existing log queries keep matching.
logger = get_logger("backend.services.knowledge.ingestion_service")


class DocumentEmbeddingMixin:
    """Chunking, embedding, and the stuck-document retry job."""

    _db_factory: Callable[[], Session]
    _embedding_client: TritonEmbeddingClient | None

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

    async def reembed_stuck_documents(self) -> int:
        """Retry chunk + embed for documents that lack their chunks. Returns the success count.

        Called periodically by the scheduler. Two cases need work: documents still in
        'uploaded', and chunked or approved documents with text but no chunks (a caregiver
        can approve while the embedding service is down, which would otherwise leave the
        document invisible to senior questions forever). A successful embed moves 'uploaded'
        to 'chunked' and writes chunks, so each document is processed until it succeeds and
        then never again.
        """
        if self._embedding_client is None:
            return 0

        db: Session = self._db_factory()
        try:
            has_chunks = (
                select(KnowledgeDocumentChunk.id)
                .where(KnowledgeDocumentChunk.document_id == KnowledgeDocument.id)
                .exists()
            )
            missing_chunks = and_(
                KnowledgeDocument.status.in_(["chunked", "approved"]),
                # Same notion of "has text" as _split_source_text (any non-whitespace), so a
                # whitespace-only document is never selected again after chunking to nothing.
                KnowledgeDocument.source_text.regexp_match(r"\S"),
                ~has_chunks,
            )
            doc_ids = list(
                db.execute(
                    select(KnowledgeDocument.id)
                    .where(or_(KnowledgeDocument.status == "uploaded", missing_chunks))
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
