from __future__ import annotations

import pytest

from backend.services.guided_task.completion.response import ResponseEvaluator, build_evaluators


@pytest.mark.asyncio
async def test_confirmed_evidence_completes():
    result = await ResponseEvaluator().is_complete(
        session=None, step=None, evidence={"confirmed": True}
    )

    assert result.complete is True
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_unconfirmed_evidence_not_complete():
    result = await ResponseEvaluator().is_complete(
        session=None, step=None, evidence={"confirmed": False}
    )

    assert result.complete is False
    assert result.reason == "not_confirmed"


def test_build_evaluators_includes_response_and_configured_assists():
    evaluators = build_evaluators({"kinds": ["vision_confirm"]})

    assert [e.kind for e in evaluators] == ["response", "vision_confirm"]
