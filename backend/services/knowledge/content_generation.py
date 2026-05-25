"""LLM-assisted paraphrase, quiz suggestion, and voice instruction generation.

Phase 4: full implementation. All generation is review-gated: the caregiver
must approve before anything reaches the senior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.integrations.llm import LLMModelRegistry, LLMProvider
from backend.models.knowledge import KnowledgeDocument

logger = get_logger(__name__)


# -- Result dataclasses ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParaphraseSuggestion:
    title: str
    body_text: str
    voice_instruction: str = ""


@dataclass(frozen=True, slots=True)
class QuizQuestionSuggestion:
    question_type: Literal["multiple_choice", "open_ended"]
    question_text: str
    choices: list[dict[str, Any]] = field(default_factory=list)
    expected_answer: str = ""
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class QuizSuggestion:
    title: str
    intro_voice_template: str = ""
    voice_instruction: str = ""
    questions: list[QuizQuestionSuggestion] = field(default_factory=list)


# -- Service -----------------------------------------------------------------


class ContentGenerationService:
    """Generates paraphrases, quiz drafts, and voice instructions via LLM."""

    def __init__(self, db_factory, llm_model_registry: LLMModelRegistry) -> None:
        self._db_factory = db_factory
        self._llm_registry = llm_model_registry

    # -- paraphrase ---------------------------------------------------------

    async def suggest_paraphrase(
        self, document_id: int, *, model_id: str | None = None
    ) -> ParaphraseSuggestion:
        """Generate a paraphrased info card from a knowledge document's source_text."""
        doc = self._get_document(document_id)
        model_id = model_id or settings.as_str("knowledge.paraphrase_model")
        provider = self._require_provider(model_id)

        prompt = _PARAPHRASE_PROMPT.format(source_text=doc.source_text[:8000])
        response = await provider.call(prompt)

        return self._parse_paraphrase(response, doc.title)

    # -- quiz suggestion ----------------------------------------------------

    async def suggest_quiz(
        self,
        document_id: int,
        *,
        num_questions: int = 5,
        mix: Literal["mc_only", "mixed"] = "mixed",
        model_id: str | None = None,
    ) -> QuizSuggestion:
        """Generate a quiz draft from a knowledge document's source_text."""
        doc = self._get_document(document_id)
        model_id = model_id or settings.as_str("knowledge.quiz_generation_model")
        provider = self._require_provider(model_id)

        q_type_instruction = (
            "Include a mix of multiple_choice and open_ended questions."
            if mix == "mixed"
            else "All questions should be multiple_choice."
        )
        prompt = _QUIZ_PROMPT.format(
            source_text=doc.source_text[:8000],
            num_questions=num_questions,
            q_type_instruction=q_type_instruction,
        )
        response = await provider.call(prompt)

        return self._parse_quiz(response, doc.title)

    # -- voice instruction --------------------------------------------------

    async def suggest_voice_instruction(
        self,
        document_id: int,
        resource_type: Literal["info_card", "quiz"],
        *,
        model_id: str | None = None,
    ) -> str:
        """Generate a voice instruction for an info card or quiz."""
        doc = self._get_document(document_id)
        model_id = model_id or settings.as_str("knowledge.paraphrase_model")
        provider = self._require_provider(model_id)

        prompt = _VOICE_INSTRUCTION_PROMPT.format(
            source_text=doc.source_text[:4000],
            resource_type=resource_type,
            title=doc.title,
        )
        response = await provider.call(prompt)
        return response.strip().strip('"').strip("'")

    # -- quiz question regeneration -----------------------------------------

    async def regenerate_question(
        self,
        document_id: int,
        question_type: str,
        existing_text: str = "",
        *,
        model_id: str | None = None,
    ) -> QuizQuestionSuggestion:
        """Regenerate a single quiz question."""
        _validate_question_type(question_type)
        doc = self._get_document(document_id)
        model_id = model_id or settings.as_str("knowledge.quiz_generation_model")
        provider = self._require_provider(model_id)

        prompt = _REGENERATE_QUESTION_PROMPT.format(
            source_text=doc.source_text[:6000],
            question_type=question_type,
            existing_text=existing_text,
        )
        response = await provider.call(prompt)
        return self._parse_single_question(response, question_type)

    # -- open-ended grading -------------------------------------------------

    async def grade_open_ended(
        self, question_text: str, expected_answer: str, senior_response: str
    ) -> bool:
        """Grade an open-ended quiz response against the expected answer."""
        model_id = settings.as_str("knowledge.quiz_generation_model")
        provider = self._require_provider(model_id)

        prompt = _GRADING_PROMPT.format(
            question_text=question_text,
            expected_answer=expected_answer,
            senior_response=senior_response,
        )
        response = await provider.call(prompt)
        response_clean = response.strip().lower()
        return response_clean.startswith("correct") or "correct" in response_clean[:20]

    # -- helpers ------------------------------------------------------------

    def _require_provider(self, model_id: str) -> LLMProvider:
        provider = self._llm_registry.get_provider(model_id)
        if provider is None:
            raise RuntimeError(f"LLM model {model_id!r} not available")
        return provider

    def _get_document(self, document_id: int) -> KnowledgeDocument:
        db: Session = self._db_factory()
        try:
            doc = db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
            ).scalar_one_or_none()
            if doc is None:
                raise ValueError(f"Knowledge document {document_id} not found")
            return doc
        finally:
            db.close()

    def _parse_paraphrase(self, response: str, fallback_title: str) -> ParaphraseSuggestion:
        """Parse LLM response into ParaphraseSuggestion. Robust to bad JSON."""
        try:
            data = _extract_json(response)
            return ParaphraseSuggestion(
                title=data.get("title", fallback_title),
                body_text=data.get("body_text", response[:500]),
                voice_instruction=data.get("voice_instruction", ""),
            )
        except Exception:
            # Fallback: use first line as title, rest as body
            lines = response.strip().split("\n", 1)
            title = lines[0].strip().lstrip("#").strip()[:200] if lines else fallback_title
            body = lines[1].strip()[:2000] if len(lines) > 1 else response[:2000]
            return ParaphraseSuggestion(title=title, body_text=body)

    def _parse_quiz(self, response: str, fallback_title: str) -> QuizSuggestion:
        """Parse LLM response into QuizSuggestion."""
        try:
            data = _extract_json(response)
            questions = []
            for q in data.get("questions", []):
                questions.append(
                    QuizQuestionSuggestion(
                        question_type=q.get("question_type", "multiple_choice"),
                        question_text=q.get("question_text", ""),
                        choices=q.get("choices", []),
                        expected_answer=q.get("expected_answer", ""),
                        explanation=q.get("explanation", ""),
                    )
                )
            return QuizSuggestion(
                title=data.get("title", f"Quiz: {fallback_title}"),
                intro_voice_template=data.get("intro_voice_template", ""),
                voice_instruction=data.get("voice_instruction", ""),
                questions=questions,
            )
        except Exception:
            return QuizSuggestion(title=f"Quiz: {fallback_title}")

    def _parse_single_question(self, response: str, question_type: str) -> QuizQuestionSuggestion:
        """Parse a single regenerated question."""
        _validate_question_type(question_type)
        try:
            data = _extract_json(response)
            return QuizQuestionSuggestion(
                question_type=cast(Literal["multiple_choice", "open_ended"], question_type),
                question_text=data.get("question_text", response[:500]),
                choices=data.get("choices", []),
                expected_answer=data.get("expected_answer", ""),
                explanation=data.get("explanation", ""),
            )
        except Exception:
            return QuizQuestionSuggestion(
                question_type=cast(Literal["multiple_choice", "open_ended"], question_type),
                question_text=response.strip()[:500],
            )


# -- helpers ------------------------------------------------------------------

_VALID_QTYPES: set[str] = {"multiple_choice", "open_ended"}


def _validate_question_type(question_type: str) -> None:
    if question_type not in _VALID_QTYPES:
        raise ValueError(f"Invalid question_type: {question_type!r}")


def _extract_json(text: str) -> dict:
    """Extract a JSON object from text that may have markdown fences or commentary."""
    text = text.strip()
    # Try to find JSON between ``` fences
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()
    # Try to find first { or [
    brace = text.find("{")
    bracket = text.find("[")
    if brace >= 0 and (bracket < 0 or brace < bracket):
        text = text[brace:]
        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = text[: i + 1]
                    break
    return json.loads(text)


# -- Prompt templates --------------------------------------------------------


_PARAPHRASE_PROMPT = """You are helping a caregiver create an information card for a senior citizen. Rewrite the following source text into a clear, simple, warm, and easy-to-understand format.

Source text:
{source_text}

Return a JSON object with these keys:
- "title": A short, warm title for the card (max 100 chars)
- "body_text": The paraphrased content in 2-4 simple sentences. Use plain language a senior can easily understand.
- "voice_instruction": A short instruction for the AI voice assistant on how to deliver this card (e.g. "Read this warmly and slowly. Pause between sentences.")

Return ONLY the JSON object, no other text."""


_QUIZ_PROMPT = """You are helping a caregiver create a quiz for a senior citizen based on the following source text. The quiz tests the senior's memory and understanding of personal facts.

Source text:
{source_text}

Create a quiz with {num_questions} questions. {q_type_instruction}

For multiple_choice questions, provide 3-4 choices, clearly marking the correct one with "is_correct": true.

Return a JSON object with these keys:
- "title": A short title for the quiz
- "intro_voice_template": A warm introduction the AI voice assistant will speak before starting (e.g. "Let's see how well you remember!")
- "voice_instruction": A short instruction for how the AI should conduct this quiz
- "questions": An array of question objects, each with:
  - "question_type": "multiple_choice" or "open_ended"
  - "question_text": The question
  - "choices": [{{"id": "a", "text": "...", "is_correct": true/false}}, ...] (for MC only)
  - "expected_answer": The correct answer (for open_ended, describe what a correct response looks like)
  - "explanation": A brief explanation of the correct answer

Keep questions simple and directly related to the source text. The senior should be able to answer from their personal knowledge.

Return ONLY the JSON object, no other text."""


_VOICE_INSTRUCTION_PROMPT = """You are helping a caregiver set up voice delivery instructions for an AI voice assistant. The AI will deliver a {resource_type} to a senior citizen.

The {resource_type} is based on this source text:
Title: {title}
Content: {source_text}

Write a short (1-3 sentence) instruction for the AI voice assistant on how to deliver this {resource_type}. Consider:
- The tone (warm, calm, encouraging)
- The pace (slow, clear)
- Any special context the AI should know

Return ONLY the instruction text, no quotes, no JSON wrapper."""


_REGENERATE_QUESTION_PROMPT = """Regenerate a single quiz question based on this source text.

Source text:
{source_text}

The question type must be: {question_type}
The previous question was: {existing_text}

Return a JSON object with:
- "question_text": The new question
- "choices": [{{"id": "a", "text": "...", "is_correct": true/false}}, ...] (for multiple_choice only)
- "expected_answer": The correct answer
- "explanation": Brief explanation

Return ONLY the JSON object, no other text."""


_GRADING_PROMPT = """You are grading a senior citizen's answer to a quiz question. Be generous and kind in your judgment. The senior may express the correct idea in simple or imperfect language.

Question: {question_text}
Expected answer: {expected_answer}
Senior's response: {senior_response}

Does the senior's response convey the key idea from the expected answer? Answer with exactly one word: "correct" or "incorrect"."""
