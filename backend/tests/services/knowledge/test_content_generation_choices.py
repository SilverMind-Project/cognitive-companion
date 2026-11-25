"""Drafted quiz choices are normalized into a shape that can be saved."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.knowledge.content_generation import (
    ContentGenerationService,
    normalize_choices,
)


def test_missing_blank_and_repeated_ids_get_free_letters() -> None:
    choices = normalize_choices(
        [
            {"text": "Boston", "is_correct": True},
            {"id": "a", "text": "Seattle"},
            {"id": "A", "text": "Denver"},
            {"id": " ", "text": "Austin"},
        ]
    )

    assert [c["id"] for c in choices] == ["a", "b", "c", "d"]
    assert [c["is_correct"] for c in choices] == [True, False, False, False]


def test_valid_ids_are_kept_and_empty_choices_dropped() -> None:
    choices = normalize_choices(
        [{"id": "x", "text": " Tea "}, {"id": "y", "text": ""}, "not a choice", {"id": "z"}]
    )

    assert choices == [{"id": "x", "text": "Tea", "is_correct": False}]


def test_non_list_yields_no_choices() -> None:
    assert normalize_choices(None) == []
    assert normalize_choices({"id": "a"}) == []


def test_parsed_quiz_draft_always_has_saveable_choice_ids() -> None:
    """The prompt asks for ids but cannot enforce them; a draft without ids used to fail
    to save with 422."""
    svc = ContentGenerationService(db_factory=None, llm_model_registry=None)  # type: ignore[arg-type]
    response = json.dumps(
        {
            "title": "Family",
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "Where does Priya live?",
                    "choices": [{"text": "Boston", "is_correct": True}, {"text": "Seattle"}],
                }
            ],
        }
    )

    draft = svc._parse_quiz(response, "Family")

    assert [c["id"] for c in draft.questions[0].choices] == ["a", "b"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_reply", "expected"),
    [
        ("correct", True),
        ("Correct.", True),
        ("Yes, correct!", True),
        ("incorrect", False),
        ("Incorrect. The resident said a different city.", False),
        ("That answer is incorrect.", False),
    ],
)
async def test_grade_open_ended_distinguishes_incorrect_from_correct(
    raw_reply: str, expected: bool
) -> None:
    provider = SimpleNamespace(call=AsyncMock(return_value=raw_reply))
    registry = SimpleNamespace(get_provider=lambda _model_id: provider)
    svc = ContentGenerationService(db_factory=None, llm_model_registry=registry)  # type: ignore[arg-type]

    result = await svc.grade_open_ended("Where does Priya live?", "Boston", "Seattle")

    assert result is expected
