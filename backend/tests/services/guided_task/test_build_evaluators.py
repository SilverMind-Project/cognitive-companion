from __future__ import annotations

from dataclasses import dataclass

from backend.services.guided_task.completion.base import CompletionResult
from backend.services.guided_task.completion.response import build_evaluators, evaluate_completion


@dataclass
class _Session:
    id: int = 1


@dataclass
class _Step:
    ord: int = 0


class _Evaluator:
    def __init__(self, kind: str, complete: bool) -> None:
        self.kind = kind
        self._complete = complete

    async def is_complete(self, *, session, step, evidence) -> CompletionResult:
        return CompletionResult(self._complete, 1.0 if self._complete else 0.0, self.kind)


def test_response_always_included() -> None:
    evaluators = build_evaluators({"kinds": ["vision_confirm"]})

    assert [evaluator.kind for evaluator in evaluators][:2] == ["response", "vision_confirm"]


async def test_any_mode_completes_on_first_gate() -> None:
    evaluation = await evaluate_completion(
        evaluators=[_Evaluator("response", False), _Evaluator("vision_confirm", True)],
        mode="any",
        session=_Session(),
        step=_Step(),
        evidence={},
    )

    assert evaluation.result.complete is True
    assert evaluation.result.reason == "vision_confirm"


async def test_all_mode_requires_all_gates() -> None:
    incomplete = await evaluate_completion(
        evaluators=[_Evaluator("response", True), _Evaluator("vision_confirm", False)],
        mode="all",
        session=_Session(),
        step=_Step(),
        evidence={},
    )
    complete = await evaluate_completion(
        evaluators=[_Evaluator("response", True), _Evaluator("vision_confirm", True)],
        mode="all",
        session=_Session(),
        step=_Step(),
        evidence={},
    )

    assert incomplete.result.complete is False
    assert complete.result.complete is True
