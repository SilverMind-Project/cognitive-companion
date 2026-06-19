"""Response-gated guided-task completion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.logging import get_logger
from backend.services.guided_task.completion.activity import (
    ActivitySignalEvaluator,
    ZonePresenceEvaluator,
)
from backend.services.guided_task.completion.base import CompletionEvaluator, CompletionResult
from backend.services.guided_task.completion.vision import VisionEvaluator, VisionEventRecorder

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


@dataclass(frozen=True)
class GateEvaluation:
    result: CompletionResult
    details: list[dict[str, Any]]


def build_evaluators(
    gate_config: dict | None,
    *,
    activity_service: Any | None = None,
    zone_service: Any | None = None,
    person_location: Any | None = None,
    bucketizer: Any | None = None,
    camera_topology: Any | None = None,
    identity_resolver: Any | None = None,
    gate_runner: Any | None = None,
    camera_source_resolver: Any | None = None,
    event_aggregator: Any | None = None,
    settings: Any | None = None,
    event_recorder: VisionEventRecorder | None = None,
) -> list[CompletionEvaluator]:
    """Build completion evaluators named by ``completion_gate.kinds``.

    The response gate is always included, so verbal confirmation remains a
    supported completion path even when perception assists are configured.
    """
    kinds = (gate_config or {}).get("kinds") or ["response"]
    ordered_kinds = ["response", *[str(kind) for kind in kinds if kind != "response"]]
    evaluators: list[CompletionEvaluator] = []
    unsupported: set[str] = set()
    for kind in ordered_kinds:
        if kind == "response":
            if not any(evaluator.kind == "response" for evaluator in evaluators):
                evaluators.append(ResponseEvaluator())
        elif kind == "vision_confirm":
            evaluators.append(
                VisionEvaluator(
                    gate_config=gate_config,
                    zone_service=zone_service,
                    person_location=person_location,
                    bucketizer=bucketizer,
                    camera_topology=camera_topology,
                    identity_resolver=identity_resolver,
                    gate_runner=gate_runner,
                    camera_source_resolver=camera_source_resolver,
                    event_aggregator=event_aggregator,
                    settings=settings,
                    event_recorder=event_recorder,
                )
            )
        elif kind == "activity_signal":
            evaluators.append(
                ActivitySignalEvaluator(
                    activity_service=activity_service,
                    gate_config=gate_config,
                )
            )
        elif kind == "zone_presence":
            evaluators.append(
                ZonePresenceEvaluator(zone_service=zone_service, gate_config=gate_config)
            )
        else:
            unsupported.add(kind)
    if unsupported:
        logger.warning("guided_completion_unsupported_kinds", kinds=sorted(unsupported))
    return evaluators


async def evaluate_completion(
    *,
    evaluators: list[CompletionEvaluator],
    mode: str,
    session: Any,
    step: Any,
    evidence: dict,
) -> GateEvaluation:
    results: list[tuple[str, CompletionResult]] = []
    for evaluator in evaluators:
        result = await evaluator.is_complete(session=session, step=step, evidence=evidence)
        results.append((evaluator.kind, result))
        if mode != "all" and result.complete:
            return GateEvaluation(result=result, details=_details(results))

    if mode == "all" and results and all(result.complete for _kind, result in results):
        weakest = min(results, key=lambda item: item[1].confidence)[1]
        return GateEvaluation(
            result=CompletionResult(True, weakest.confidence, "all_gates_complete"),
            details=_details(results),
        )
    if mode == "all":
        return GateEvaluation(
            result=CompletionResult(False, 0.0, "not_all_gates_complete"),
            details=_details(results),
        )

    best = max(
        (result for _kind, result in results), key=lambda item: item.confidence, default=None
    )
    if best is None:
        best = CompletionResult(False, 0.0, "no_completion_evaluators")
    return GateEvaluation(result=best, details=_details(results))


def _details(results: list[tuple[str, CompletionResult]]) -> list[dict[str, Any]]:
    return [
        {
            "kind": kind,
            "complete": result.complete,
            "confidence": result.confidence,
            "reason": result.reason,
        }
        for kind, result in results
    ]
