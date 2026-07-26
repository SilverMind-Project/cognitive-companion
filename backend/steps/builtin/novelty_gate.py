"""Novelty gate: skip downstream analysis when the scene has not changed.

Compares the current CLIP embedding (``scene_analysis``'s ``scene_embedding``
by default) against the last embedding seen for a ``scope`` (one cache slot
per rule and camera by default). When the cosine distance is below
``min_distance``, the scene is unchanged since the last check and the
tier-3/4 model calls downstream can be skipped.

Authoring pattern::

    scene_analysis -> novelty_gate -> condition(novel == true) -> llm_call

``scene_analysis`` (tier-2) still runs every tick; this gate only saves the
more expensive reasoning/vision calls further downstream. scene-analysis-service
has no embed-only route today (only ``/analyze``, which runs the combined
detect/describe/embed/hazards pipeline behind ``run_*`` flags, and ``/describe``,
which is Florence-2 caption only); a cheaper embed-only wiring is future work if
that service ever adds one. Fails open (``novel=true``) whenever no embedding is
available, since the gate must never suppress analysis because an upstream step
broke.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.template import render_template
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.pipeline_data_manager import resolve_pipeline_value
from backend.steps import StepRegistry
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

_DEFAULT_SCOPE_TEMPLATE = "{{rule}}:{{camera}}"
_DEFAULT_TTL_MINUTES = 120.0
_MAX_CACHE_SCOPES = 1000


def _cosine_distance(a: list[float], b: list[float]) -> float | None:
    """1 - cosine similarity. ``None`` when the vectors can't be meaningfully compared."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    return 1.0 - (dot / (norm_a * norm_b))


@StepRegistry.register
class NoveltyGateHandler(StepHandler):
    """Perception step: cache-compare a CLIP embedding per scope (DL5/DL-M09)."""

    def __init__(
        self,
        *,
        time_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_cache_scopes: int = _MAX_CACHE_SCOPES,
    ) -> None:
        self._time_fn = time_fn
        self._max_cache_scopes = max_cache_scopes
        # Module-level (per-handler-instance) TTL-bounded cache. The registry
        # constructs exactly one instance of this handler for the process
        # lifetime (backend.core.registry.PluginRegistry.register), so this
        # dict persists across pipeline executions, which is the point: it
        # remembers the last embedding seen for each scope.
        self._cache: dict[str, tuple[list[float], datetime]] = {}

    def _cache_write(self, scope: str, embedding: list[float], now: datetime) -> None:
        """Insert/refresh a scope's entry, evicting the oldest-*written* scope
        first if a genuinely new key would push the cache past
        ``max_cache_scopes``. Bounds memory when rules or cameras are
        deleted/renamed and their scope keys stop being read but would
        otherwise sit in the cache indefinitely (TTL only expires an entry on
        the next read of that same scope, never on its own).

        This is oldest-write, not true LRU: ``cached_at`` only advances on a
        write, and a write only happens on ``no_previous``/``stale``/``novel``
        (see ``execute()``). A scope that is polled constantly but never
        drifts (the common steady-state case) stops writing and its
        ``cached_at`` freezes, making it look like the *oldest* entry and a
        prime eviction target, while a noisy/drifting scope keeps refreshing
        itself and survives. Acceptable here because eviction only triggers
        once genuinely distinct scopes (rule+camera pairs) exceed
        ``max_cache_scopes``, which this codebase's rule/camera cardinality is
        nowhere near; this is a memory safety net for deleted/renamed
        rules/cameras, not an LRU cache for a hot working set.
        """
        if scope not in self._cache and len(self._cache) >= self._max_cache_scopes:
            oldest_scope = min(self._cache, key=lambda s: self._cache[s][1])
            del self._cache[oldest_scope]
        self._cache[scope] = (embedding, now)

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="novelty_gate",
            display_name="Novelty Gate",
            category="perception",
            icon="mdi-image-filter-center-focus",
            description=(
                "Skip downstream analysis when the scene has not changed since the "
                "last check for this scope. Compares a CLIP embedding (e.g. "
                "scene_analysis's scene_embedding) by cosine distance. Authoring "
                "pattern: scene_analysis -> novelty_gate -> condition(novel == true) "
                "-> llm_call. tier-2 scene_analysis still runs every tick; this step "
                "only gates the more expensive tier-3/4 calls further downstream."
            ),
            config_schema={
                "type": "object",
                "properties": {
                    "embedding_key": {
                        "type": "string",
                        "default": "scene_embedding",
                        "description": (
                            "Dotted pipeline_data path to a CLIP embedding "
                            "(list of floats)."
                        ),
                    },
                    "scope": {
                        "type": "string",
                        "default": _DEFAULT_SCOPE_TEMPLATE,
                        "description": (
                            "Template resolving to one cache slot key. Defaults to "
                            "one slot per rule and camera ({{rule}} / {{camera}} / "
                            "{{room_name}} / {{sensor_id}} are available)."
                        ),
                    },
                    "min_distance": {
                        "type": ["number", "null"],
                        "minimum": 0.0,
                        "description": (
                            "Cosine distance at or above this counts as novel. "
                            "Leave blank to use the novelty_gate.min_distance setting."
                        ),
                    },
                    "ttl_minutes": {
                        "type": "number",
                        "default": _DEFAULT_TTL_MINUTES,
                        "minimum": 1,
                        "description": (
                            "A cached embedding older than this counts as novel "
                            "regardless of distance, so a slowly drifting scene "
                            "eventually re-triggers."
                        ),
                    },
                },
                "required": [],
            },
            default_config={
                "embedding_key": "scene_embedding",
                "scope": _DEFAULT_SCOPE_TEMPLATE,
                "min_distance": None,
                "ttl_minutes": _DEFAULT_TTL_MINUTES,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "novel": {"type": "boolean"},
                    "distance": {"type": ["number", "null"]},
                    "reason": {
                        "type": "string",
                        "enum": ["no_previous", "stale", "compared", "no_embedding"],
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
        embedding_key: str = config.get("embedding_key") or "scene_embedding"
        embedding = resolve_pipeline_value(pipeline_data, embedding_key)

        if not isinstance(embedding, list) or not embedding:
            logger.info("novelty_gate_no_embedding", embedding_key=embedding_key)
            return StepResult(data={"novel": True, "distance": None, "reason": "no_embedding"})

        scope_template: str = config.get("scope") or _DEFAULT_SCOPE_TEMPLATE
        scope_vars = {
            "rule": execution.rule.name if execution.rule else "",
            "camera": trigger.sensor_id or "",
            "room_name": trigger.room_name or "",
            "sensor_id": trigger.sensor_id or "",
        }
        scope = render_template(scope_template, pipeline_data, scope_vars)

        raw_min_distance = config.get("min_distance")
        min_distance = (
            float(raw_min_distance)
            if raw_min_distance is not None
            else float(settings.get("novelty_gate.min_distance", 0.06))
        )
        ttl_minutes = float(config.get("ttl_minutes") or _DEFAULT_TTL_MINUTES)

        now = self._time_fn()
        cached = self._cache.get(scope)

        if cached is None:
            self._cache_write(scope, embedding, now)
            return StepResult(data={"novel": True, "distance": None, "reason": "no_previous"})

        cached_embedding, cached_at = cached
        if now - cached_at > timedelta(minutes=ttl_minutes):
            self._cache_write(scope, embedding, now)
            return StepResult(data={"novel": True, "distance": None, "reason": "stale"})

        distance = _cosine_distance(embedding, cached_embedding)
        if distance is None:
            # Dimension mismatch or a zero-norm vector: can't meaningfully
            # compare, so fail open rather than guess.
            self._cache_write(scope, embedding, now)
            return StepResult(data={"novel": True, "distance": None, "reason": "no_previous"})

        novel = distance >= min_distance
        if novel:
            self._cache_write(scope, embedding, now)

        return StepResult(data={"novel": novel, "distance": distance, "reason": "compared"})
