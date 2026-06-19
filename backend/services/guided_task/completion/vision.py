"""Vision-confirm completion evaluator for guided tasks."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from backend.core.logging import get_logger
from backend.integrations.llm.json_utils import parse_llm_json
from backend.services.guided_task._verdict_utils import _bounded_float
from backend.services.guided_task.camera_selection import IdentityResolver, select_cameras
from backend.services.guided_task.completion.base import CompletionResult
from backend.services.media_window_frames import CtsFrameWindowConfig, collect_recent_cts_frames

logger = get_logger(__name__)

_VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "complete": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["complete", "confidence", "reason"],
    "additionalProperties": False,
}


VisionEventRecorder = Callable[[int, int | None, dict[str, Any]], None | Awaitable[None]]


class VisionEvaluator:
    """Completion gate backed by selected CTS frames and a vision-capable LLM."""

    kind = "vision_confirm"

    def __init__(
        self,
        *,
        gate_config: dict | None,
        zone_service: Any | None,
        person_location: Any | None,
        bucketizer: Any | None,
        camera_topology: Any | None,
        identity_resolver: IdentityResolver | None,
        llm_model_registry: Any | None,
        minio_client: Any | None,
        event_recorder: VisionEventRecorder | None = None,
    ) -> None:
        self._gate_config = gate_config or {}
        self._zone_service = zone_service
        self._person_location = person_location
        self._bucketizer = bucketizer
        self._camera_topology = camera_topology
        self._identity_resolver = identity_resolver
        self._llm_model_registry = llm_model_registry
        self._minio_client = minio_client
        self._event_recorder = event_recorder

    async def is_complete(
        self,
        *,
        session: Any,
        step: Any,
        evidence: dict,
    ) -> CompletionResult:
        vision_cfg = self._gate_config.get("vision") or self._gate_config.get("vision_confirm") or {}
        cameras = await select_cameras(
            person_id=session.person_id,
            step=step,
            zone_service=self._zone_service,
            person_location=self._person_location,
            bucketizer=self._bucketizer,
            camera_topology=self._camera_topology,
            identity_resolver=self._identity_resolver,
            max_cameras=int(vision_cfg.get("max_cameras", 3)),
        )
        if not cameras:
            await self._record(session, step, cameras, False, 0.0, "no_cameras")
            return CompletionResult(False, 0.0, "no_cameras")

        collected = await collect_recent_cts_frames(
            bucketizer=self._bucketizer,
            minio_client=self._minio_client,
            config=CtsFrameWindowConfig(
                window_id=f"guided_vision_{session.id}_{step.ord}",
                cameras=cameras,
                lookback_s=float(vision_cfg.get("lookback_s", 10.0)),
                lookahead_s=float(vision_cfg.get("lookahead_s", 0.0)),
                sample_period_s=float(vision_cfg.get("sample_period_s", 1.0)),
                max_frames=int(vision_cfg.get("max_frames", 9)),
                now=evidence.get("now"),
            ),
        )
        if not collected.images:
            await self._record(session, step, cameras, False, 0.0, "no_images")
            return CompletionResult(False, 0.0, "no_images")

        provider, model_id = self._provider(vision_cfg)
        if provider is None:
            await self._record(session, step, cameras, False, 0.0, "vision_model_unavailable")
            return CompletionResult(False, 0.0, "vision_model_unavailable")

        prompt = _build_prompt(vision_cfg)
        raw = await provider.call(
            prompt=prompt,
            media_paths=collected.images,
            media_type="image",
            response_schema=_VISION_RESPONSE_SCHEMA,
            temperature=0.0,
        )
        parsed = parse_llm_json(raw or "")
        if not isinstance(parsed, dict):
            await self._record(session, step, cameras, False, 0.0, "parse_failed")
            return CompletionResult(False, 0.0, "parse_failed")

        complete = parsed.get("complete") is True
        confidence = _bounded_float(parsed.get("confidence"))
        reason = str(parsed.get("reason") or "vision_confirm")
        min_confidence = float(vision_cfg.get("min_confidence", 0.7))
        accepted = complete and confidence >= min_confidence
        if not accepted and complete:
            reason = "low_confidence"

        logger.info(
            "vision_confirm_result",
            session_id=session.id,
            step_ord=step.ord,
            model_id=model_id,
            complete=accepted,
            confidence=confidence,
            cameras=cameras,
        )
        await self._record(session, step, cameras, accepted, confidence, reason)
        return CompletionResult(accepted, confidence, reason)

    def _provider(self, vision_cfg: dict[str, Any]) -> tuple[Any | None, str | None]:
        registry = self._llm_model_registry
        if registry is None:
            return None, None
        model_id = vision_cfg.get("model_id")
        if not model_id:
            for cfg in registry.all_configs():
                if "vision" in cfg.capabilities:
                    model_id = cfg.id
                    break
        if not model_id:
            return None, None
        cfg = registry.get_config(str(model_id))
        if cfg is None or "vision" not in cfg.capabilities:
            return None, str(model_id)
        return registry.get_provider(str(model_id)), str(model_id)

    async def _record(
        self,
        session: Any,
        step: Any,
        cameras: list[str],
        complete: bool,
        confidence: float,
        reason: str,
    ) -> None:
        if self._event_recorder is None:
            return
        detail = {
            "cameras": cameras,
            "complete": complete,
            "confidence": confidence,
            "reason": reason,
        }
        result = self._event_recorder(session.id, getattr(step, "ord", None), detail)
        if inspect.isawaitable(result):
            await result


def _build_prompt(vision_cfg: dict[str, Any]) -> str:
    done_description = vision_cfg.get("done_description") or vision_cfg.get("description")
    if not done_description:
        done_description = "the resident has completed the current routine step"
    return (
        "You are checking whether a guided-care routine step appears complete. "
        "Use only visible evidence from the image sequence. "
        f"The step is complete if: {done_description}. "
        'Respond with strict JSON: {"complete": bool, "confidence": 0..1, "reason": "..."}'
    )
