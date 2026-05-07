"""Unit tests for KnowledgeQueryService (no DB required)."""

import pytest

from backend.services.knowledge.query_service import KnowledgeAnswer, KnowledgeQueryService


class TestKnowledgeAnswer:
    def test_no_answer_dataclass(self):
        result = KnowledgeAnswer(
            query_text="test",
            answer_text="",
            source_document_ids=(),
            source_chunk_ids=(),
            top_similarity=0.0,
            answered_via="no_answer",
        )
        assert result.answered_via == "no_answer"
        assert result.answer_text == ""

    def test_rag_answer_shape(self):
        result = KnowledgeAnswer(
            query_text="How many?",
            answer_text="Three.",
            source_document_ids=(1, 2),
            source_chunk_ids=(5, 6, 7),
            top_similarity=0.85,
            answered_via="rag",
        )
        assert result.answered_via == "rag"
        assert len(result.source_document_ids) == 2
        assert result.top_similarity > 0.5

    def test_dataclass_is_frozen(self):
        result = KnowledgeAnswer(
            query_text="q",
            answer_text="a",
            source_document_ids=(),
            source_chunk_ids=(),
            top_similarity=0.0,
            answered_via="no_answer",
        )
        with pytest.raises(Exception):
            result.answer_text = "modified"  # type: ignore[misc]


class TestQueryServiceNoClient:
    """Tests that don't need a database or embedding client."""

    @pytest.mark.asyncio
    async def test_no_client_returns_no_answer(self):
        svc = KnowledgeQueryService(
            db_factory=None, embedding_client=None, llm_model_registry=None
        )
        answer = await svc.answer("test query")
        assert answer.answered_via == "no_answer"
        assert answer.query_text == "test query"

    def test_log_query_no_db(self):
        def _failing_factory():
            raise RuntimeError("no DB available")
        svc = KnowledgeQueryService(db_factory=_failing_factory)
        answer = KnowledgeAnswer(
            query_text="q",
            answer_text="a",
            source_document_ids=(1,),
            source_chunk_ids=(2,),
            top_similarity=0.8,
            answered_via="rag",
        )
        result_id = svc.log_query(answer, channel="voice", latency_ms=100)
        assert result_id == -1  # returns -1 when DB unavailable
