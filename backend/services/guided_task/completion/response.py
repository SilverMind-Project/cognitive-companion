"""Response-gated guided-task completion."""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.services.guided_task.completion.base import CompletionEvaluator, CompletionResult

logger = get_logger(__name__)


class ResponseEvaluator:
    """Completion gate driven by an explicit resident confirmation."""

    kind = "response"

    async def is_complete(
        self,
        *,
        session: Any,
        step: Any,
        evidence: dict,
    ) -> CompletionResult:
        if evidence.get("confirmed") is True:
            return CompletionResult(complete=True, confidence=1.0, reason="confirmed")
        return CompletionResult(complete=False, confidence=0.0, reason="not_confirmed")


def build_evaluators(gate_config: dict | None) -> list[CompletionEvaluator]:
    """Build M3 completion evaluators.

    M3 always includes the response gate. Non-response kinds are logged and
    ignored until M7 implements them.
    """
    kinds = (gate_config or {}).get("kinds") or ["response"]
    unsupported = sorted({kind for kind in kinds if kind != "response"})
    if unsupported:
        logger.warning("guided_completion_unsupported_kinds", kinds=unsupported)
    return [ResponseEvaluator()]
