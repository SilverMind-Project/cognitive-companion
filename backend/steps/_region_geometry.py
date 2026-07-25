"""Pure image-space region geometry helpers for the ``region_presence`` step.

Coordinate space
----------------
Regions and normalized bboxes here are in normalized ``[0, 1]`` IMAGE space
(top-left origin), identical to ``image_crop``'s region schema. This is
never floor-space ``RoomZone`` meters (M00 glossary rule / guided-companion
coordinate rule): the two spaces are never compared or mixed.

Bbox space (verified 2026-07-21, widened 2026-07-25 DL-M06)
-------------------------------------------------------------
Read ``backend/integrations/scene_analysis_client.py`` and
``scene-analysis-service/app/services/detector.py``: ``SceneDetection.bbox``
is always ``[x1, y1, x2, y2]`` in PIXEL coordinates relative to the analyzed
image (see the ``Detection`` docstring in ``detector.py``). ``scene_analysis``
now decodes each analyzed image locally (it already has the bytes) and
attaches ``image_width``/``image_height`` to every detection dict in both
``scene_detections`` and ``scene_images[*].scene_detections``, so a pixel
bbox from the default producer normalizes without a second fetch or a model
call.

This module never infers coordinate space from value magnitude. A
detection is treated as already-normalized only via an explicit
``bbox_normalized: true`` key; a pixel bbox is normalized only when
``image_width``/``image_height`` (or ``frame_width``/``frame_height``,
``original_width``/``original_height``) sibling keys accompany the
detection dict. Absent both signals (e.g. an image that failed to decode),
the detection is skipped with reason ``"unknown_bbox_space"`` rather than
guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from shapely.geometry import Polygon
from shapely.geometry.point import Point
from shapely.prepared import prep

from backend.core.logging import get_logger

logger = get_logger(__name__)

AnchorMode = Literal["center", "bottom_center"]
RegionEvalMode = Literal["anchor", "overlap"]

_WIDTH_KEYS = ("image_width", "frame_width", "original_width")
_HEIGHT_KEYS = ("image_height", "frame_height", "original_height")
_CAMERA_KEYS = ("camera_id", "sensor_id", "source_camera_id", "source_sensor_id")


@dataclass(frozen=True)
class NormalizedRegion:
    """A configured region in normalized ``[0, 1]`` image space."""

    id: str
    name: str
    rect: tuple[float, float, float, float] | None = None  # (x, y, width, height)
    points: tuple[tuple[float, float], ...] | None = None  # polygon vertices
    camera_id: str | None = None

    def to_shapely(self) -> Polygon:
        """Build a Shapely polygon for this region (rect or explicit points)."""
        if self.points is not None:
            return Polygon(self.points)
        x, y, width, height = self.rect  # type: ignore[misc]
        return Polygon([(x, y), (x + width, y), (x + width, y + height), (x, y + height)])

    @classmethod
    def from_config(cls, entry: Mapping[str, Any]) -> NormalizedRegion:
        """Build a region from a raw config dict (rect or polygon shape)."""
        region_id = str(entry["id"])
        name = str(entry.get("name", region_id))
        raw_camera_id = entry.get("camera_id")
        camera_id = str(raw_camera_id) if raw_camera_id else None

        if "points" in entry:
            points = tuple((float(p[0]), float(p[1])) for p in entry["points"])
            return cls(id=region_id, name=name, points=points, camera_id=camera_id)

        rect = (
            float(entry["x"]),
            float(entry["y"]),
            float(entry["width"]),
            float(entry["height"]),
        )
        return cls(id=region_id, name=name, rect=rect, camera_id=camera_id)


@dataclass(frozen=True)
class RegionHit:
    """A single detection-in-region match."""

    region_id: str
    region_name: str
    detection_index: int
    label: str
    confidence: float
    anchor: tuple[float, float]


def anchor_point(bbox: Sequence[float], mode: AnchorMode) -> tuple[float, float]:
    """Return the position-proxy anchor point for *bbox*, in the same units as *bbox*.

    ``bottom_center`` (the default) uses the foot midpoint: a standing
    person's bbox center lands inside a counter/table region behind them
    when they are tall, so the bottom-center anchor is the position proxy,
    not the geometric bbox center.
    """
    x1, y1, x2, y2 = bbox
    if mode == "center":
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return ((x1 + x2) / 2.0, y2)


def detection_camera_id(detection: Mapping[str, Any]) -> str | None:
    """Best-effort camera/sensor attribution for a detection dict, or None."""
    for key in _CAMERA_KEYS:
        value = detection.get(key)
        if value:
            return str(value)
    return None


def _first_positive(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
    return None


def _normalize_bbox(
    detection: Mapping[str, Any],
    bbox: Sequence[float],
) -> tuple[tuple[float, float, float, float] | None, str]:
    """Resolve *bbox* to normalized ``[0, 1]`` image space.

    Returns ``(normalized_bbox, "")`` on success, or ``(None, reason)`` when
    the space cannot be determined without guessing. See the module
    docstring for the trust rules.
    """
    if detection.get("bbox_normalized") is True:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])), ""

    width = _first_positive(detection, _WIDTH_KEYS)
    height = _first_positive(detection, _HEIGHT_KEYS)
    if width is None or height is None:
        return None, "unknown_bbox_space"

    return (
        float(bbox[0]) / width,
        float(bbox[1]) / height,
        float(bbox[2]) / width,
        float(bbox[3]) / height,
    ), ""


def evaluate_regions(
    detections: Sequence[Mapping[str, Any]],
    regions: Sequence[NormalizedRegion],
    *,
    mode: RegionEvalMode = "anchor",
    anchor: AnchorMode = "bottom_center",
    min_overlap: float = 0.5,
    labels: Sequence[str] = ("person",),
    min_confidence: float = 0.5,
) -> tuple[list[RegionHit], list[dict[str, Any]]]:
    """Evaluate *detections* against *regions*.

    Returns ``(hits, skipped)``. Detections are filtered to *labels*
    (case-insensitive) and *min_confidence* before geometry. Camera
    attribution is a step-level (not geometry-level) concern; see
    ``region_presence.py``.

    ``mode="anchor"`` (default): a hit is recorded when the detection's
    anchor point is covered by the region (closed boundary: a point exactly
    on the edge counts, matching the zone layer's Shapely usage).

    ``mode="overlap"``: a hit is recorded when
    ``area(bbox ∩ region) / area(bbox) >= min_overlap``.
    """
    label_set = {label.lower() for label in labels} if labels else set()
    prepared_regions = [(region, region.to_shapely()) for region in regions]

    hits: list[RegionHit] = []
    skipped: list[dict[str, Any]] = []

    for index, detection in enumerate(detections):
        label = str(detection.get("label", ""))
        confidence = float(detection.get("confidence", 0.0))
        bbox = detection.get("bbox")

        if label_set and label.lower() not in label_set:
            continue
        if confidence < min_confidence:
            continue
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            skipped.append({"reason": "invalid_bbox", "detection_index": index})
            continue

        normalized, reason = _normalize_bbox(detection, bbox)
        if normalized is None:
            skipped.append({"reason": reason, "detection_index": index})
            logger.warning(
                "region_presence_unknown_bbox_space", detection_index=index, label=label
            )
            continue

        point = anchor_point(normalized, anchor)

        if mode == "overlap":
            bbox_polygon = Polygon(
                [
                    (normalized[0], normalized[1]),
                    (normalized[2], normalized[1]),
                    (normalized[2], normalized[3]),
                    (normalized[0], normalized[3]),
                ]
            )
            bbox_area = bbox_polygon.area
            if bbox_area <= 0:
                continue
            for region, polygon in prepared_regions:
                intersection_area = polygon.intersection(bbox_polygon).area
                if (intersection_area / bbox_area) >= min_overlap:
                    hits.append(
                        RegionHit(
                            region_id=region.id,
                            region_name=region.name,
                            detection_index=index,
                            label=label,
                            confidence=confidence,
                            anchor=point,
                        )
                    )
        else:
            anchor_geom = Point(point)
            for region, polygon in prepared_regions:
                if prep(polygon).covers(anchor_geom):
                    hits.append(
                        RegionHit(
                            region_id=region.id,
                            region_name=region.name,
                            detection_index=index,
                            label=label,
                            confidence=confidence,
                            anchor=point,
                        )
                    )

    return hits, skipped
