"""knowledge_query step against the real KnowledgeQueryService and database.

Only the embedding model and the LLM are stand-ins; similarity search, tag filtering,
and the query history run for real.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from jsonschema import Draft202012Validator

from backend.models.knowledge import KnowledgeDocument, KnowledgeDocumentChunk, SeniorKnowledgeQuery
from backend.services.knowledge.query_service import KnowledgeQueryService
from backend.steps.builtin.knowledge_query import KnowledgeQueryStep

_DIM = 768


@dataclass
class _Step:
    config_json: dict
    id: int = 1


@dataclass
class _Trigger:
    room_name: str | None = "kitchen"
    sensor_id: str | None = "cam1"


@dataclass
class _Services:
    knowledge_query: KnowledgeQueryService | None


class _Embedder:
    async def embed_query(self, text: str) -> list[float]:
        return [0.05] * _DIM


class _Provider:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def call(self, prompt: str, *, caller: str = "unknown") -> str:
        self.prompts.append(prompt)
        return self.reply


class _Registry:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider

    def get_provider(self, model_id: str) -> _Provider:
        return self.provider


class _RecordingService(KnowledgeQueryService):
    """The real service, recording the per-call overrides it receives."""

    calls: list[dict]

    async def answer(self, query: str, **kwargs):  # type: ignore[override]
        self.calls.append({"query": query, **kwargs})
        return await super().answer(query, **kwargs)


@pytest.fixture
def medication_doc(db_session) -> int:
    doc = KnowledgeDocument(
        title="Medicine",
        source_text="Vasanthi takes the blue pill at 2 pm.",
        tags=["medication"],
        status="approved",
        created_by="caregiver",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.add(
        KnowledgeDocumentChunk(
            document_id=doc.id,
            chunk_index=0,
            text="Vasanthi takes the blue pill at 2 pm.",
            embedding=[0.05] * _DIM,
            char_start=0,
            char_end=37,
        )
    )
    db_session.commit()
    return doc.id


def _service(db_factory, reply: str = "The blue pill at 2 pm.") -> _RecordingService:
    svc = _RecordingService(
        db_factory=db_factory,
        embedding_client=_Embedder(),  # type: ignore[arg-type]
        llm_model_registry=_Registry(_Provider(reply)),  # type: ignore[arg-type]
    )
    svc.calls = []
    return svc


async def _run(config: dict, svc: KnowledgeQueryService | None, pipeline_data: dict | None = None):
    return await KnowledgeQueryStep().execute(
        _Step(config_json=config),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        pipeline_data or {},
        _Trigger(),  # type: ignore[arg-type]
        _Services(knowledge_query=svc),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_renders_templates_answers_and_matches_output_schema(
    db_factory, medication_doc: int
) -> None:
    svc = _service(db_factory)

    result = await _run(
        {
            "query_text": "What does {{person_name}} take in the {{trigger.room_name}}?",
            "tags": ["{{topic}}"],
        },
        svc,
        {"person_name": "Vasanthi", "topic": "medication"},
    )

    assert result.success is True
    assert svc.calls[0]["query"] == "What does Vasanthi take in the kitchen?"
    assert svc.calls[0]["tags"] == ["medication"]
    assert result.data["has_answer"] is True
    assert result.data["answered_via"] == "rag"
    assert result.data["answer_text"] == "The blue pill at 2 pm."
    assert result.data["source_document_ids"] == [medication_doc]
    assert result.data["chunks"] == ["Vasanthi takes the blue pill at 2 pm."]
    assert result.data["query_id"] is None
    schema = KnowledgeQueryStep.metadata().output_schema
    assert not list(Draft202012Validator(schema).iter_errors(result.data))
    assert set(result.data) == set(schema["properties"])


@pytest.mark.asyncio
async def test_blank_overrides_inherit_the_household_settings(
    db_factory, medication_doc: int
) -> None:
    """A pipeline answers the way the voice companion does unless the rule says otherwise."""
    svc = _service(db_factory)

    await _run({"query_text": "medicine?"}, svc)
    await _run({"query_text": "medicine?", "top_k": 3, "min_similarity": 0.4}, svc)

    assert svc.calls[0]["top_k"] is None
    assert svc.calls[0]["min_similarity"] is None
    assert svc.calls[1]["top_k"] == 3
    assert svc.calls[1]["min_similarity"] == 0.4


@pytest.mark.asyncio
async def test_declined_answer_is_not_has_answer(db_factory, medication_doc: int) -> None:
    result = await _run(
        {"query_text": "What is the wifi password?"}, _service(db_factory, "NO_ANSWER")
    )

    assert result.success is True
    assert result.data["has_answer"] is False
    assert result.data["answered_via"] == "no_answer"
    assert result.data["chunks"]  # the passages are still available downstream


@pytest.mark.asyncio
async def test_missing_service_fails_with_the_full_empty_output() -> None:
    result = await _run({"query_text": "anything"}, None)

    assert result.success is False
    assert result.data["answered_via"] == "no_answer"
    assert set(result.data) == set(KnowledgeQueryStep.metadata().output_schema["properties"])


@pytest.mark.asyncio
async def test_query_that_renders_empty_fails(db_factory, medication_doc: int) -> None:
    svc = _service(db_factory)

    result = await _run({"query_text": "   "}, svc)

    assert result.success is False
    assert svc.calls == []


@pytest.mark.asyncio
async def test_log_interaction_records_a_pipeline_history_row(
    db_session, db_factory, medication_doc: int
) -> None:
    result = await _run(
        {"query_text": "medicine?", "log_interaction": True},
        _service(db_factory),
        {"person_id": "vasanthi-amma"},
    )

    row = db_session.get(SeniorKnowledgeQuery, result.data["query_id"])
    assert row is not None
    assert row.channel == "pipeline"
    assert row.senior_id == "vasanthi-amma"
    assert row.answered_via == "rag"
