"""RAG query service: vector search + LLM synthesis for senior questions.

Phase 2: full implementation with Triton embeddings, pgvector cosine search,
and constrained LLM answer generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.llm import LLMModelRegistry
from backend.integrations.triton_embedding_client import TritonEmbeddingClient
from backend.models.knowledge import SeniorKnowledgeQuery

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    query_text: str
    answer_text: str
    source_document_ids: tuple[int, ...]
    source_chunk_ids: tuple[int, ...]
    top_similarity: float
    answered_via: Literal["rag", "no_answer"]


class KnowledgeQueryService:
    """Vector search + LLM synthesis for senior knowledge questions."""

    def __init__(
        self,
        db_factory,
        embedding_client: TritonEmbeddingClient | None = None,
        llm_model_registry: LLMModelRegistry | None = None,
    ) -> None:
        self._db_factory = db_factory
        self._embedding_client = embedding_client
        self._llm_registry = llm_model_registry

    async def answer(self, query: str) -> KnowledgeAnswer:
        """Embed query, search chunks, synthesize answer via LLM."""
        if self._embedding_client is None:
            return KnowledgeAnswer(
                query_text=query,
                answer_text="",
                source_document_ids=(),
                source_chunk_ids=(),
                top_similarity=0.0,
                answered_via="no_answer",
            )

        # 1. Embed query
        try:
            query_vec = await self._embedding_client.embed_query(query)
        except Exception:
            logger.exception("query_embed_failed")
            return KnowledgeAnswer(
                query_text=query,
                answer_text="",
                source_document_ids=(),
                source_chunk_ids=(),
                top_similarity=0.0,
                answered_via="no_answer",
            )

        # 2. Vector search
        top_k = settings.as_int("knowledge.retrieval_top_k")
        min_sim = settings.as_float("knowledge.min_similarity")

        db: Session = self._db_factory()
        try:
            vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
            rows = db.execute(
                text("""
                    SELECT
                        kdc.id AS chunk_id,
                        kdc.document_id,
                        kdc.text AS chunk_text,
                        1 - (kdc.embedding <=> :vec::vector) AS similarity
                    FROM knowledge_document_chunks kdc
                    JOIN knowledge_documents kd ON kd.id = kdc.document_id
                    WHERE kd.status = 'approved'
                    ORDER BY kdc.embedding <=> :vec::vector
                    LIMIT :topk
                """),
                {"vec": vec_str, "topk": top_k},
            ).fetchall()

            if not rows:
                return KnowledgeAnswer(
                    query_text=query,
                    answer_text="",
                    source_document_ids=(),
                    source_chunk_ids=(),
                    top_similarity=0.0,
                    answered_via="no_answer",
                )

            top_similarity = float(rows[0][3])
            if top_similarity < min_sim:
                return KnowledgeAnswer(
                    query_text=query,
                    answer_text="",
                    source_document_ids=(),
                    source_chunk_ids=(),
                    top_similarity=top_similarity,
                    answered_via="no_answer",
                )

            # 3. Build context from top chunks
            context_parts: list[str] = []
            doc_ids: set[int] = set()
            chunk_ids: list[int] = []
            for row in rows:
                chunk_ids.append(row[0])
                doc_ids.add(row[1])
                context_parts.append(row[2])

            context = "\n\n---\n\n".join(context_parts)

            # 4. LLM synthesis
            answer_text = ""
            if self._llm_registry is not None:
                answer_text = await self._synthesize(query, context)

            return KnowledgeAnswer(
                query_text=query,
                answer_text=answer_text,
                source_document_ids=tuple(sorted(doc_ids)),
                source_chunk_ids=tuple(chunk_ids),
                top_similarity=top_similarity,
                answered_via="rag",
            )
        except Exception:
            logger.exception("query_search_failed")
            return KnowledgeAnswer(
                query_text=query,
                answer_text="",
                source_document_ids=(),
                source_chunk_ids=(),
                top_similarity=0.0,
                answered_via="no_answer",
            )
        finally:
            db.close()

    async def _synthesize(self, query: str, context: str) -> str:
        """Call the configured LLM with a constrained prompt."""
        if self._llm_registry is None:
            return ""
        answer_model_id = settings.as_str("knowledge.answer_model")
        try:
            provider = self._llm_registry.get_provider(answer_model_id)
        except Exception:
            logger.exception("llm_provider_not_found", model=answer_model_id)
            return ""
        if provider is None:
            logger.warning("llm_provider_none", model=answer_model_id)
            return ""

        prompt = f"""You are a helpful assistant for a senior citizen. Answer the question using ONLY the provided context. If the context does not contain the answer, say "I don't have that information."

Context:
{context}

Question: {query}

Answer (in 1-2 simple sentences):"""

        try:
            response = await provider.call(prompt)
            return response.strip()
        except Exception:
            logger.exception("llm_synthesis_failed")
            return ""

    def log_query(
        self,
        answer: KnowledgeAnswer,
        *,
        senior_id: str | None = None,
        channel: str = "voice",
        latency_ms: int | None = None,
    ) -> int:
        """Persist a query result row. Returns the new row id."""
        db: Session | None = None
        try:
            db = self._db_factory()
            row = SeniorKnowledgeQuery(
                senior_id=senior_id,
                query_text=answer.query_text,
                answer_text=answer.answer_text,
                source_document_ids=list(answer.source_document_ids),
                source_chunk_ids=list(answer.source_chunk_ids),
                top_similarity=answer.top_similarity,
                answered_via=answer.answered_via,
                channel=channel,
                latency_ms=latency_ms,
                asked_at=datetime.now(UTC),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
        except Exception:
            if db is not None:
                db.rollback()
            logger.exception("log_query_failed")
            return -1
        finally:
            if db is not None:
                db.close()
