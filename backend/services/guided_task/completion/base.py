"""Completion evaluator protocol for guided tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class CompletionResult:
    complete: bool
    confidence: float
    reason: str


class CompletionEvaluator(Protocol):
    kind: str

    async def is_complete(
        self,
        *,
        session: Any,
        step: Any,
        evidence: dict,
    ) -> CompletionResult: ...
