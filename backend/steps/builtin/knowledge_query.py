"""Knowledge query pipeline step: ask the curated Knowledge Repository a question.

Searches caregiver-approved knowledge documents (medications, routines, family,
preferences) and synthesizes a grounded answer for downstream steps, through the same
``KnowledgeQueryService`` the voice agent's ``query_knowledge_base`` tool uses. Distinct
from ``semantic_memory_query``, which reads camera scene observations.
"""

from __future__ import annotations

import time
from typing import Any

from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.steps import StepRegistry
from backend.steps._helpers import make_trigger_vars, resolve_person_id
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


def _empty_output(query_text: str = "", error: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "query_text": query_text,
        "answer_text": "",
        "answered_via": "no_answer",
        "has_answer": False,
        "top_similarity": 0.0,
        "source_document_ids": [],
        "source_chunk_ids": [],
        "chunks": [],
        "query_id": None,
    }
    if error:
        out["error"] = error
    return out


@StepRegistry.register
class KnowledgeQueryStep(StepHandler):
    """Query approved household knowledge documents and synthesize an answer."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="knowledge_query",
            display_name="Knowledge Query",
            category="reasoning",
            icon="mdi-book-search-outline",
            description=(
                "Ask the caregiver-approved knowledge documents a question and get a "
                "grounded answer (plus the retrieved passages) for later steps."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string",
                        "description": "The question to ask. Supports {{template}} syntax.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": (
                            "Only search documents carrying any of these tags. Supports "
                            "{{template}} syntax."
                        ),
                    },
                    "top_k": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                        "maximum": 20,
                        "description": (
                            "Passages to retrieve. Blank uses knowledge.retrieval_top_k, "
                            "the same as the voice companion."
                        ),
                    },
                    "min_similarity": {
                        "type": ["number", "null"],
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": (
                            "Minimum match strength (0 to 1). Blank uses "
                            "knowledge.min_similarity, the same as the voice companion."
                        ),
                    },
                    "person_id": {
                        "type": "string",
                        "default": "",
                        "description": (
                            "Resident the question is about, for the query history; "
                            "defaults to the person in the trigger or upstream steps."
                        ),
                    },
                    "log_interaction": {
                        "type": "boolean",
                        "default": False,
                        "description": "Record the question in the Senior Knowledge Queries history.",
                    },
                },
                "required": ["query_text"],
            },
            default_config={
                "query_text": "",
                "tags": [],
                "person_id": "",
                "log_interaction": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string",
                        "description": "The question as asked, templates rendered",
                    },
                    "answer_text": {
                        "type": "string",
                        "description": "The grounded answer; empty when there is none",
                    },
                    "answered_via": {"type": "string", "enum": ["rag", "no_answer"]},
                    "has_answer": {
                        "type": "boolean",
                        "description": "True when the documents answered the question",
                    },
                    "top_similarity": {"type": "number"},
                    "source_document_ids": {"type": "array", "items": {"type": "integer"}},
                    "source_chunk_ids": {"type": "array", "items": {"type": "integer"}},
                    "chunks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The retrieved passages, strongest match first",
                    },
                    "query_id": {
                        "type": ["integer", "null"],
                        "description": "History row id when log_interaction is on",
                    },
                    "error": {
                        "type": "string",
                        "description": "Why the step failed (only on failure)",
                    },
                },
            },
            gate_safe=True,
        )

    async def execute(
        self,
        step: PipelineStep,
        execution: WorkflowExecution,
        pipeline_data: dict,
        trigger: TriggerContext,
        services: ServiceContainer,
    ) -> StepResult:
        config = step.config_json or {}
        trigger_vars = make_trigger_vars(trigger)

        query_svc = services.knowledge_query
        if query_svc is None:
            logger.error("knowledge_query_service_unavailable", step_id=step.id)
            return StepResult(success=False, data=_empty_output())

        query_text = render_template(
            str(config.get("query_text") or ""), pipeline_data, trigger_vars
        ).strip()
        if not query_text:
            return StepResult(success=False, data=_empty_output(error="query_text is empty"))

        tags = [
            rendered
            for raw in config.get("tags") or []
            if (rendered := render_template(str(raw), pipeline_data, trigger_vars).strip())
        ]
        # render_template leaves an unresolvable {{ }} in place. Searching for the braces
        # (or filtering on a literal "{{topic}}" tag) returns a confident-looking "no
        # answer" for what is really a rule-authoring mistake, so fail loudly instead.
        if "{{" in query_text or any("{{" in tag for tag in tags):
            logger.warning("knowledge_query_template_unresolved", step_id=step.id)
            return StepResult(
                success=False,
                data=_empty_output(error="a {{template}} in query_text or tags did not resolve"),
            )
        top_k = config.get("top_k")
        min_similarity = config.get("min_similarity")

        started = time.monotonic()
        answer = await query_svc.answer(
            query_text,
            tags=tags or None,
            top_k=int(top_k) if top_k is not None else None,
            min_similarity=float(min_similarity) if min_similarity is not None else None,
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        query_id: int | None = None
        if config.get("log_interaction", False):
            logged = query_svc.log_query(
                answer,
                senior_id=resolve_person_id(config, pipeline_data, trigger_vars),
                channel="pipeline",
                latency_ms=latency_ms,
            )
            query_id = logged if logged > 0 else None

        logger.info(
            "knowledge_query_step_executed",
            step_id=step.id,
            answered_via=answer.answered_via,
            source_count=len(answer.source_document_ids),
        )
        return StepResult(
            data={
                "query_text": answer.query_text,
                "answer_text": answer.answer_text,
                "answered_via": answer.answered_via,
                "has_answer": answer.answered_via == "rag",
                "top_similarity": float(answer.top_similarity),
                "source_document_ids": list(answer.source_document_ids),
                "source_chunk_ids": list(answer.source_chunk_ids),
                "chunks": list(answer.chunks),
                "query_id": query_id,
            }
        )
