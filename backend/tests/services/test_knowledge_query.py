"""Knowledge model wiring and RAG answer semantics when synthesis yields nothing."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import yaml

from backend.bootstrap.knowledge import KNOWLEDGE_MODEL_SETTING_KEYS, validate_knowledge_models
from backend.core.config import settings
from backend.integrations.llm import LLMModelRegistry
from backend.models.knowledge import KnowledgeDocument, KnowledgeDocumentChunk
from backend.services.knowledge.query_service import KnowledgeQueryService

_DIM = 768


def test_configured_knowledge_models_exist_in_settings_llm_models() -> None:
    """The shipped settings.yaml must name registered models (an alias silently broke RAG)."""
    with open("config/settings.yaml", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    registered = {m["id"] for m in raw["llm"]["models"]}
    knowledge = raw["knowledge"]
    for key in KNOWLEDGE_MODEL_SETTING_KEYS:
        model_id = knowledge[key.split(".", 1)[1]]
        assert model_id in registered, f"{key}={model_id!r} is not an llm.models id"


def test_validate_knowledge_models_accepts_loaded_registry() -> None:
    registry = LLMModelRegistry()
    registry.load_from_settings()
    assert validate_knowledge_models(settings, registry) == []


def test_validate_knowledge_models_reports_unknown_ids() -> None:
    registry = LLMModelRegistry()
    registry.load_from_settings()
    fake_settings = Mock()
    fake_settings.as_str.side_effect = lambda key, allow_empty=True: (
        "gemma4_26b" if key == "knowledge.answer_model" else "gemma-4-26B-A4B-it"
    )

    assert validate_knowledge_models(fake_settings, registry) == ["knowledge.answer_model"]


class _Embedder:
    async def embed_query(self, text: str) -> list[float]:
        return [0.05] * _DIM


class _RegistryWithoutModel:
    def get_provider(self, model_id: str) -> None:
        return None


@pytest.fixture
def approved_chunk(db_session) -> tuple[int, int]:
    doc = KnowledgeDocument(
        title="Family",
        source_text="Priya lives in Boston.",
        tags=[],
        status="approved",
        created_by="caregiver",
    )
    db_session.add(doc)
    db_session.flush()
    chunk = KnowledgeDocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        text="Priya lives in Boston.",
        embedding=[0.05] * _DIM,
        char_start=0,
        char_end=22,
    )
    db_session.add(chunk)
    db_session.commit()
    return doc.id, chunk.id


async def test_empty_synthesis_is_no_answer_with_sources_kept(
    db_factory, approved_chunk: tuple[int, int]
) -> None:
    doc_id, chunk_id = approved_chunk
    svc = KnowledgeQueryService(
        db_factory=db_factory,
        embedding_client=_Embedder(),  # type: ignore[arg-type]
        llm_model_registry=_RegistryWithoutModel(),  # type: ignore[arg-type]
    )

    answer = await svc.answer("Where does Priya live?")

    # Retrieval matched, but an empty answer must never be reported as found.
    assert answer.answered_via == "no_answer"
    assert answer.answer_text == ""
    assert answer.source_document_ids == (doc_id,)
    assert answer.source_chunk_ids == (chunk_id,)
    assert answer.top_similarity > 0.99


class _Provider:
    async def call(self, prompt: str) -> str:
        assert "Priya lives in Boston." in prompt
        return " Priya lives in Boston. "


class _RegistryWithModel:
    def get_provider(self, model_id: str) -> _Provider:
        return _Provider()


async def test_vector_search_runs_against_pgvector_and_answers(
    db_factory, approved_chunk: tuple[int, int]
) -> None:
    """Exercises the real similarity SQL; a bind-parameter cast bug once failed every search."""
    doc_id, _ = approved_chunk
    svc = KnowledgeQueryService(
        db_factory=db_factory,
        embedding_client=_Embedder(),  # type: ignore[arg-type]
        llm_model_registry=_RegistryWithModel(),  # type: ignore[arg-type]
    )

    answer = await svc.answer("Where does Priya live?")

    assert answer.answered_via == "rag"
    assert answer.answer_text == "Priya lives in Boston."
    assert answer.source_document_ids == (doc_id,)
