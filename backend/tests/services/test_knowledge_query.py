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
    """Same call contract as an LLMProvider: the caller tag is a keyword argument."""

    def __init__(self, reply: str = " Priya lives in Boston. ") -> None:
        self.reply = reply
        self.prompts: list[str] = []
        self.callers: list[str] = []

    async def call(self, prompt: str, *, caller: str = "unknown") -> str:
        self.prompts.append(prompt)
        self.callers.append(caller)
        return self.reply


class _RegistryWithModel:
    def __init__(self, provider: _Provider | None = None) -> None:
        self.provider = provider or _Provider()

    def get_provider(self, model_id: str) -> _Provider:
        return self.provider


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
    assert "Priya lives in Boston." in answer.chunks[0]


def _service(db_factory, provider: _Provider) -> KnowledgeQueryService:
    return KnowledgeQueryService(
        db_factory=db_factory,
        embedding_client=_Embedder(),  # type: ignore[arg-type]
        llm_model_registry=_RegistryWithModel(provider),  # type: ignore[arg-type]
    )


async def test_declined_synthesis_is_no_answer_not_a_rag_answer(
    db_factory, approved_chunk: tuple[int, int]
) -> None:
    """Retrieved context that lacks the answer used to come back as answered_via=rag
    carrying the model's refusal sentence; a has_answer check then saw a false yes."""
    doc_id, _ = approved_chunk
    provider = _Provider(reply="  NO_ANSWER. ")

    answer = await _service(db_factory, provider).answer("What is the wifi password?")

    assert answer.answered_via == "no_answer"
    assert answer.answer_text == ""
    assert answer.source_document_ids == (doc_id,)  # still on the audit row
    assert "reply with exactly NO_ANSWER" in provider.prompts[0]


async def test_token_with_trailing_reasoning_is_still_no_answer(
    db_factory, approved_chunk: tuple[int, int]
) -> None:
    """A reply that adds text after the token must not be spoken as an answer."""
    provider = _Provider(reply="NO_ANSWER. The context only says where Priya lives.")

    answer = await _service(db_factory, provider).answer("What is the wifi password?")

    assert answer.answered_via == "no_answer"
    assert answer.answer_text == ""


async def test_synthesis_is_attributed_in_admission_control(
    db_factory, approved_chunk: tuple[int, int]
) -> None:
    provider = _Provider()

    await _service(db_factory, provider).answer("Where does Priya live?")

    assert provider.callers == ["knowledge_rag"]


async def test_tag_filter_keeps_only_documents_with_a_matching_tag(
    db_session, db_factory, approved_chunk: tuple[int, int]
) -> None:
    doc_id, _ = approved_chunk
    tagged = KnowledgeDocument(
        title="Medicine",
        source_text="Take the blue pill at 8 am.",
        tags=["medication"],
        status="approved",
        created_by="caregiver",
    )
    db_session.add(tagged)
    db_session.flush()
    db_session.add(
        KnowledgeDocumentChunk(
            document_id=tagged.id,
            chunk_index=0,
            text="Take the blue pill at 8 am.",
            embedding=[0.05] * _DIM,
            char_start=0,
            char_end=27,
        )
    )
    db_session.commit()
    svc = _service(db_factory, _Provider())

    filtered = await svc.answer("medicine", tags=["medication", "unrelated"])
    unfiltered = await svc.answer("medicine")

    assert filtered.source_document_ids == (tagged.id,)
    assert set(unfiltered.source_document_ids) == {doc_id, tagged.id}


async def test_per_call_overrides_replace_the_household_settings(
    db_factory, approved_chunk: tuple[int, int]
) -> None:
    svc = _service(db_factory, _Provider())

    strict = await svc.answer("Where does Priya live?", min_similarity=1.01)
    limited = await svc.answer("Where does Priya live?", top_k=1)

    assert strict.answered_via == "no_answer"  # above any possible cosine similarity
    assert strict.answer_text == ""
    assert len(limited.source_chunk_ids) == 1
