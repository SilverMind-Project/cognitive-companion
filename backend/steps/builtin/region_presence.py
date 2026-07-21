"""Region presence pipeline step.

Answers "is a person in this part of the image" from detections an earlier
step (``scene_analysis``) already produced, without spending a model call on
a geometry question. See ``backend/steps/_region_geometry.py`` for the
coordinate-space rules and bbox-space handling.

Result keys written to ``pipeline_data``
-----------------------------------------
``in_region``
    ``True`` if any detection matched any configured region.

``count``
    Number of region hits (a detection matching two regions counts twice).

``hits``
    List of per-match dicts: ``region_id``, ``region_name``, ``label``,
    ``confidence``, ``anchor``, ``detection_index``.

``per_region``
    Hit count keyed by ``region_id``.

``skipped``
    Structured reasons for detections/config that could not be evaluated
    (``no_detections``, ``no_regions``, ``invalid_bbox``,
    ``unknown_bbox_space``, ``camera_filter_unavailable``).

``evaluated_at``
    ISO8601 timestamp of the evaluation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.core.logging import get_logger
from backend.models.pipeline import PipelineStep, WorkflowExecution
from backend.services.pipeline_data_manager import resolve_pipeline_value
from backend.steps import StepRegistry
from backend.steps._region_geometry import (
    NormalizedRegion,
    detection_camera_id,
    evaluate_regions,
)
from backend.steps.base import (
    ServiceContainer,
    StepHandler,
    StepMetadata,
    StepResult,
    TriggerContext,
)

logger = get_logger(__name__)

_RECT_REGION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "name", "x", "y", "width", "height"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "name": {"type": "string"},
        "x": {"type": "number", "minimum": 0, "maximum": 1},
        "y": {"type": "number", "minimum": 0, "maximum": 1},
        "width": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "height": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "camera_id": {"type": "string"},
    },
}

_POLYGON_REGION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "name", "points"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "name": {"type": "string"},
        "points": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "camera_id": {"type": "string"},
    },
}


def _empty_output(reason: str) -> dict[str, Any]:
    return {
        "in_region": False,
        "count": 0,
        "hits": [],
        "per_region": {},
        "skipped": [{"reason": reason}],
        "evaluated_at": datetime.now(UTC).isoformat(),
    }


@StepRegistry.register
class RegionPresenceHandler(StepHandler):
    """Test person bboxes against configured image-space regions."""

    @classmethod
    def metadata(cls) -> StepMetadata:
        return StepMetadata(
            type_name="region_presence",
            display_name="Region Presence",
            category="perception",
            icon="mdi-vector-polygon",
            description=(
                "Test detections from an earlier perception step against configured "
                "normalized image-space regions (rects or polygons). Never spends a "
                "model call on a geometry question."
            ),
            tags=("region", "geometry", "presence"),
            config_schema={
                "type": "object",
                "properties": {
                    "detections_key": {
                        "type": "string",
                        "default": "scene_detections",
                        "description": "Dotted pipeline_data path to the detection list.",
                    },
                    "regions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "oneOf": [_RECT_REGION_SCHEMA, _POLYGON_REGION_SCHEMA],
                        },
                        "default": [],
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["anchor", "overlap"],
                        "default": "anchor",
                    },
                    "anchor": {
                        "type": "string",
                        "enum": ["bottom_center", "center"],
                        "default": "bottom_center",
                    },
                    "min_overlap": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.5,
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["person"],
                    },
                    "min_confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.5,
                    },
                },
            },
            default_config={
                "detections_key": "scene_detections",
                "regions": [],
                "mode": "anchor",
                "anchor": "bottom_center",
                "min_overlap": 0.5,
                "labels": ["person"],
                "min_confidence": 0.5,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "in_region": {"type": "boolean"},
                    "count": {"type": "integer"},
                    "hits": {"type": "array", "items": {"type": "object"}},
                    "per_region": {"type": "object"},
                    "skipped": {"type": "array", "items": {"type": "object"}},
                    "evaluated_at": {"type": "string"},
                },
                "required": [
                    "in_region",
                    "count",
                    "hits",
                    "per_region",
                    "skipped",
                    "evaluated_at",
                ],
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
        detections_key = str(config.get("detections_key", "scene_detections"))
        raw_detections = resolve_pipeline_value(pipeline_data, detections_key, default=[])

        if not isinstance(raw_detections, list) or not raw_detections:
            return StepResult(data=_empty_output("no_detections"))

        region_configs: list[dict] = config.get("regions") or []
        if not region_configs:
            return StepResult(data=_empty_output("no_regions"))

        regions = [NormalizedRegion.from_config(entry) for entry in region_configs]
        mode = config.get("mode", "anchor")
        anchor_mode = config.get("anchor", "bottom_center")
        min_overlap = float(config.get("min_overlap", 0.5))
        labels = config.get("labels") or ["person"]
        min_confidence = float(config.get("min_confidence", 0.5))

        hits, skipped = evaluate_regions(
            raw_detections,
            regions,
            mode=mode,
            anchor=anchor_mode,
            min_overlap=min_overlap,
            labels=labels,
            min_confidence=min_confidence,
        )

        # -- Per-region camera_id scoping (best-effort; never fails the step) --
        camera_scoped_ids = {region.id for region in regions if region.camera_id}
        if camera_scoped_ids:
            attribution_available = any(
                detection_camera_id(d) is not None for d in raw_detections
            )
            if attribution_available:
                region_by_id = {region.id: region for region in regions}
                filtered_hits = []
                for hit in hits:
                    region = region_by_id[hit.region_id]
                    if region.camera_id:
                        det_camera = detection_camera_id(raw_detections[hit.detection_index])
                        if det_camera != region.camera_id:
                            continue
                    filtered_hits.append(hit)
                hits = filtered_hits
            else:
                skipped.append({"reason": "camera_filter_unavailable"})

        per_region: dict[str, int] = {}
        for hit in hits:
            per_region[hit.region_id] = per_region.get(hit.region_id, 0) + 1

        logger.info(
            "region_presence_evaluated",
            detections=len(raw_detections),
            regions=len(regions),
            hits=len(hits),
        )

        return StepResult(
            data={
                "in_region": len(hits) > 0,
                "count": len(hits),
                "hits": [
                    {
                        "region_id": hit.region_id,
                        "region_name": hit.region_name,
                        "label": hit.label,
                        "confidence": hit.confidence,
                        "anchor": list(hit.anchor),
                        "detection_index": hit.detection_index,
                    }
                    for hit in hits
                ],
                "per_region": per_region,
                "skipped": skipped,
                "evaluated_at": datetime.now(UTC).isoformat(),
            }
        )
