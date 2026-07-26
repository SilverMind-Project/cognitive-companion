"""media_presign pipeline step.

Presigns MinIO object names into URLs consumable by downstream steps
(``llm_call``, ``notification``), without uploading or re-deriving anything.
The motivating case is a ``dementia_signal`` trigger's evidence context (see
``DementiaSignalSubscriber.handle`` in ``backend/services/cts/subscriber.py``,
which puts the CTS signal's ``context_json`` under the ``evidence`` key of the
``fire_event`` payload; ``PipelineExecutor`` threads that payload into
``pipeline_data["trigger_event"]``), which carries bare MinIO object names
(``today_best_keyframe_objects`` / ``yesterday_best_keyframe_objects``) rather
than URLs a vision step can fetch directly. The step is intentionally generic
(not hygiene-specific): any rule that receives object-name references in
trigger or prior-step context can use it.

No separate CTS-vs-CC bucket config: CTS and Cognitive Companion share one
MinIO endpoint and bucket today (confirmed by ``backend/routers/cts.py``'s
``GET /cts/frames/{key}`` proxy, which serves CTS-produced ``minio_key``
values through the plain ``get_minio_client()`` singleton, the same client
this step uses via ``services.minio_client``). A milestone draft anticipated
a per-source bucket config key; it was dropped as dead config once this was
verified against the running code, not assumed from the CTS/CC settings
files alone.
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.pipeline_data_manager import resolve_pipeline_value
from backend.steps import StepRegistry
from backend.steps._media_cache import register_media_cache_row
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)


def _collect_object_names(config: dict[str, Any], pipeline_data: dict[str, Any]) -> list[str]:
    """Resolve every configured dotted path to object names, deduped in order.

    Each path may resolve to a single object name or a list of them (both
    ``DailyAppearanceProfile``'s keyframe lists on the CTS side are lists).
    """
    paths = config.get("object_names_key") or []
    if not isinstance(paths, list):
        return []

    names: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not isinstance(path, str) or not path:
            continue
        raw = resolve_pipeline_value(pipeline_data, path)
        if raw is None:
            continue
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for value in values:
            name = str(value)
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


@StepRegistry.register
class MediaPresignHandler(StepHandler):
    """Presign MinIO object names referenced in trigger or pipeline context."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="media_presign",
            display_name="Presign Media",
            category="perception",
            icon="mdi-image-lock",
            description=(
                "Resolve MinIO object names from trigger or pipeline context into "
                "presigned URLs, registering each as a MediaCache row for cleanup. "
                "Use this to turn a signal's evidence keyframe references into "
                "images an llm_call or notification step can use."
            ),
            tags=("image", "media", "cts", "signal"),
            config_schema={
                "type": "object",
                "properties": {
                    "object_names_key": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                        "description": (
                            "Dotted pipeline_data paths, each resolving to a MinIO "
                            "object name or a list of them, e.g. "
                            "'trigger_event.evidence.today_best_keyframe_objects'. "
                            "All resolved names are concatenated and de-duplicated."
                        ),
                    },
                    "retention_minutes": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 1440,
                        "default": 240,
                    },
                    "output_key": {
                        "type": "string",
                        "default": "presigned_images",
                        "description": "pipeline_data key for the list of presigned URLs.",
                    },
                },
            },
            default_config={
                "object_names_key": [],
                "retention_minutes": 240,
                "output_key": "presigned_images",
            },
            output_schema={
                "type": "object",
                "properties": {
                    "presigned_images": {"type": "array", "items": {"type": "string"}},
                    "objects": {"type": "array", "items": {"type": "object"}},
                    "count": {"type": "integer"},
                    "skipped": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["objects", "count", "skipped"],
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
        output_key = str(config.get("output_key") or "presigned_images").strip() or (
            "presigned_images"
        )

        if services.minio_client is None:
            return StepResult(
                success=False,
                data={
                    output_key: [],
                    "objects": [],
                    "count": 0,
                    "skipped": [],
                    "error": "MinIO client is not available",
                },
            )

        retention_minutes = int(config.get("retention_minutes", 240))
        object_names = _collect_object_names(config, pipeline_data)

        urls: list[str] = []
        objects: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for object_name in object_names:
            exists = await services.minio_client.async_object_exists(object_name)
            if not exists:
                skipped.append({"object_name": object_name, "reason": "not_found"})
                continue

            try:
                url = services.minio_client.generate_presigned_url(object_name)
            except Exception:
                logger.exception("media_presign_generate_url_error", object_name=object_name)
                skipped.append({"object_name": object_name, "reason": "presign_failed"})
                continue

            register_media_cache_row(
                services,
                object_name,
                url,
                sensor_id=None,
                retention_minutes=retention_minutes,
            )
            urls.append(url)
            objects.append({"object_name": object_name, "url": url})

        return StepResult(
            data={
                output_key: urls,
                "objects": objects,
                "count": len(objects),
                "skipped": skipped,
            },
        )
