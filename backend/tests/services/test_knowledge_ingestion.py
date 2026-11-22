"""KnowledgeIngestionService: single-session chunk + embed, re-embed, and delete purge."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.core.exceptions import AppError, ConflictError
from backend.models.knowledge import InfoCard, KnowledgeDocument, KnowledgeDocumentChunk
from backend.services.knowledge.ingestion_service import KnowledgeIngestionService

_DIM = 768
_TEXT = "Priya is your granddaughter. She lives in Boston and visits every Sunday afternoon."


class _FakeEmbedder:
    """Deterministic stand-in for the Triton text embedder (pgvector dim 768)."""

    def __init__(self) -> None:
        self.calls = 0
        self.fail = False
        self.on_embed: Callable[[], None] | None = None

    async def embed_chunks(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise ConnectionError("triton unavailable")
        if self.on_embed is not None:
            self.on_embed()
        return [[0.01 * (i + 1)] * _DIM for i in range(len(texts))]

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * _DIM


@pytest.fixture
def embedder() -> _FakeEmbedder:
    return _FakeEmbedder()


@pytest.fixture
def image_pipeline() -> Mock:
    pipeline = Mock()
    pipeline.purge_prefix = AsyncMock()
    return pipeline


def _service(db_factory, image_pipeline: Mock, embedder: _FakeEmbedder | None):
    return KnowledgeIngestionService(
        db_factory=db_factory,
        minio_client=Mock(),
        image_pipeline=image_pipeline,
        embedding_client=embedder,
    )


@pytest.fixture
def ingestion(db_factory, image_pipeline: Mock, embedder: _FakeEmbedder):
    return _service(db_factory, image_pipeline, embedder)


def _persisted(db_factory, doc_id: int) -> tuple[str, int]:
    """Status and chunk count as a brand-new session sees them (what the retry job sees)."""
    db: Session = db_factory()
    try:
        status = db.execute(
            select(KnowledgeDocument.status).where(KnowledgeDocument.id == doc_id)
        ).scalar_one()
        chunks = db.execute(
            select(func.count(KnowledgeDocumentChunk.id)).where(
                KnowledgeDocumentChunk.document_id == doc_id
            )
        ).scalar_one()
        return status, chunks
    finally:
        db.close()


async def _create(ingestion: KnowledgeIngestionService, text: str = _TEXT) -> KnowledgeDocument:
    return await ingestion.create_document(
        title="Family", source_text=text, tags=["family"], created_by="caregiver", images=[]
    )


async def test_create_document_transitions_to_chunked_in_database(
    ingestion: KnowledgeIngestionService, db_factory
) -> None:
    doc = await _create(ingestion)

    assert doc.status == "chunked"
    assert len(doc.chunks) >= 1
    assert _persisted(db_factory, doc.id) == ("chunked", len(doc.chunks))


async def test_reembed_stuck_documents_does_not_reprocess_chunked_docs(
    db_factory, image_pipeline: Mock, embedder: _FakeEmbedder
) -> None:
    offline = _service(db_factory, image_pipeline, None)
    doc = await _create(offline)
    assert _persisted(db_factory, doc.id) == ("uploaded", 0)

    online = _service(db_factory, image_pipeline, embedder)
    assert await online.reembed_stuck_documents() == 1
    assert _persisted(db_factory, doc.id)[0] == "chunked"

    calls_after_first_run = embedder.calls
    assert await online.reembed_stuck_documents() == 0
    assert embedder.calls == calls_after_first_run


async def test_failed_embed_stays_uploaded_and_is_not_counted(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder, db_factory
) -> None:
    embedder.fail = True
    doc = await _create(ingestion)
    assert _persisted(db_factory, doc.id) == ("uploaded", 0)

    assert await ingestion.reembed_stuck_documents() == 0
    assert _persisted(db_factory, doc.id) == ("uploaded", 0)


async def test_whitespace_document_is_chunked_with_no_chunks(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder, db_factory
) -> None:
    doc = await _create(ingestion, text="   \n  ")
    assert _persisted(db_factory, doc.id) == ("chunked", 0)
    assert embedder.calls == 0
    assert await ingestion.reembed_stuck_documents() == 0


async def test_text_edited_during_embed_discards_stale_chunks(
    db_factory, image_pipeline: Mock, embedder: _FakeEmbedder
) -> None:
    offline = _service(db_factory, image_pipeline, None)
    doc = await _create(offline)

    def caregiver_edits_meanwhile() -> None:
        db = db_factory()
        try:
            db.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == doc.id)
                .values(source_text="Priya moved to Seattle.")
            )
            db.commit()
        finally:
            db.close()

    embedder.on_embed = caregiver_edits_meanwhile
    online = _service(db_factory, image_pipeline, embedder)

    assert await online.reembed_stuck_documents() == 0
    assert _persisted(db_factory, doc.id) == ("uploaded", 0)


async def test_update_document_source_change_re_embeds(
    ingestion: KnowledgeIngestionService, db_factory
) -> None:
    doc = await _create(ingestion)
    ingestion.approve_document(doc.id)

    updated = await ingestion.update_document(doc.id, source_text="Priya moved to Seattle.")

    # Changed content goes back through review; the new chunks are written immediately.
    assert updated.status == "chunked"
    assert [c.text for c in updated.chunks] == ["Priya moved to Seattle."]
    assert _persisted(db_factory, doc.id) == ("chunked", 1)


async def test_reembed_document_keeps_approval(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder, db_factory
) -> None:
    doc = await _create(ingestion)
    ingestion.approve_document(doc.id)
    calls = embedder.calls

    reembedded = await ingestion.reembed_document(doc.id)

    assert reembedded.status == "approved"
    assert embedder.calls == calls + 1
    assert _persisted(db_factory, doc.id)[0] == "approved"


async def test_reembed_document_rejects_archived_and_reports_embed_failure(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder
) -> None:
    doc = await _create(ingestion)

    embedder.fail = True
    with pytest.raises(AppError) as unavailable:
        await ingestion.reembed_document(doc.id)
    assert unavailable.value.status_code == 503

    ingestion.archive_document(doc.id)
    with pytest.raises(ConflictError):
        await ingestion.reembed_document(doc.id)


async def test_delete_document_purges_minio_prefix_and_guards_references(
    ingestion: KnowledgeIngestionService, image_pipeline: Mock, db_session, db_factory
) -> None:
    referenced = await _create(ingestion)
    db_session.add(
        InfoCard(title="Visit", body_text="Sunday", document_id=referenced.id, status="draft")
    )
    db_session.commit()

    with pytest.raises(ConflictError):
        await ingestion.delete_document(referenced.id)
    image_pipeline.purge_prefix.assert_not_awaited()

    unreferenced = await _create(ingestion)
    await ingestion.delete_document(unreferenced.id)

    image_pipeline.purge_prefix.assert_awaited_once_with(f"knowledge/{unreferenced.id}/")
    assert ingestion.get_document(unreferenced.id) is None


async def test_delete_document_survives_purge_failure(
    ingestion: KnowledgeIngestionService, image_pipeline: Mock
) -> None:
    doc = await _create(ingestion)
    image_pipeline.purge_prefix.side_effect = ConnectionError("minio down")

    await ingestion.delete_document(doc.id)

    assert ingestion.get_document(doc.id) is None


async def test_approved_document_without_chunks_is_retried(
    db_factory, image_pipeline: Mock, embedder: _FakeEmbedder
) -> None:
    offline = _service(db_factory, image_pipeline, None)
    doc = await _create(offline)
    offline.approve_document(doc.id)  # approved while the embedding service was down
    assert _persisted(db_factory, doc.id) == ("approved", 0)

    online = _service(db_factory, image_pipeline, embedder)
    assert await online.reembed_stuck_documents() == 1
    status, chunks = _persisted(db_factory, doc.id)
    assert status == "approved"
    assert chunks >= 1
    assert await online.reembed_stuck_documents() == 0


async def test_whitespace_document_is_never_reselected(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder, db_factory
) -> None:
    doc = await _create(ingestion, text="\n\n\t  \n")
    ingestion.approve_document(doc.id)
    assert _persisted(db_factory, doc.id) == ("approved", 0)

    assert await ingestion.reembed_stuck_documents() == 0
    assert embedder.calls == 0


async def test_resaving_identical_text_keeps_approval(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder
) -> None:
    doc = await _create(ingestion)
    ingestion.approve_document(doc.id)
    calls = embedder.calls

    updated = await ingestion.update_document(doc.id, source_text=_TEXT, title="Family (edited)")

    assert updated.status == "approved"
    assert updated.title == "Family (edited)"
    assert embedder.calls == calls


async def test_editing_archived_document_keeps_it_archived_until_restored(
    ingestion: KnowledgeIngestionService, embedder: _FakeEmbedder, db_factory
) -> None:
    doc = await _create(ingestion)
    ingestion.archive_document(doc.id)
    calls = embedder.calls

    edited = await ingestion.update_document(doc.id, source_text="Priya moved to Seattle.")

    assert edited.status == "archived"
    assert edited.archived_at is not None
    assert embedder.calls == calls

    restored = ingestion.restore_document(doc.id)
    assert restored.status == "uploaded"
    assert restored.archived_at is None
    assert await ingestion.reembed_stuck_documents() == 1
    assert _persisted(db_factory, doc.id)[0] == "chunked"
    assert [c.text for c in ingestion.get_document(doc.id).chunks] == ["Priya moved to Seattle."]
