"""Unit tests for backend/steps/_region_geometry.py.

Pure geometry, no DB, no pipeline machinery.
"""

from __future__ import annotations

from backend.steps._region_geometry import (
    NormalizedRegion,
    anchor_point,
    detection_camera_id,
    evaluate_regions,
)


def _rect_region(region_id="r1", name="Region 1", x=0.0, y=0.5, width=1.0, height=0.5):
    return NormalizedRegion(id=region_id, name=name, rect=(x, y, width, height))


def _detection(bbox, label="person", confidence=0.9, **extra):
    return {"label": label, "confidence": confidence, "bbox": bbox, **extra}


# ---------------------------------------------------------------------------
# anchor_point
# ---------------------------------------------------------------------------


def test_anchor_bottom_center_inside_rect_center_outside():
    """A tall bbox whose foot point is in the bottom region but whose bbox
    center lands above the region boundary (in the top half)."""
    # bbox spans y from 0.1 (head) to 0.6 (feet); region covers y in [0.5, 1.0].
    bbox = (0.4, 0.1, 0.6, 0.6)
    region = _rect_region(x=0.0, y=0.5, width=1.0, height=0.5)

    bottom_hits, _ = evaluate_regions(
        [_detection(bbox, bbox_normalized=True)], [region], anchor="bottom_center"
    )
    center_hits, _ = evaluate_regions(
        [_detection(bbox, bbox_normalized=True)], [region], anchor="center"
    )

    assert len(bottom_hits) == 1
    assert len(center_hits) == 0


def test_anchor_center_differs_from_bottom_when_center_inside():
    """A short bbox near the top whose center is inside a top region but
    whose foot point falls into a bottom region."""
    bbox = (0.4, 0.05, 0.6, 0.55)  # center y = 0.30, foot y = 0.55
    top_region = _rect_region(region_id="top", x=0.0, y=0.0, width=1.0, height=0.4)

    center_hits, _ = evaluate_regions(
        [_detection(bbox, bbox_normalized=True)], [top_region], anchor="center"
    )
    bottom_hits, _ = evaluate_regions(
        [_detection(bbox, bbox_normalized=True)], [top_region], anchor="bottom_center"
    )

    assert len(center_hits) == 1
    assert len(bottom_hits) == 0


def test_anchor_point_pure_math():
    assert anchor_point((0.0, 0.0, 1.0, 1.0), "center") == (0.5, 0.5)
    assert anchor_point((0.0, 0.0, 1.0, 1.0), "bottom_center") == (0.5, 1.0)


# ---------------------------------------------------------------------------
# Boundary / polygon semantics
# ---------------------------------------------------------------------------


def test_point_on_boundary_counts():
    """A point exactly on the region edge counts as covered (closed boundary)."""
    region = _rect_region(x=0.5, y=0.0, width=0.5, height=1.0)
    # Foot point lands exactly at x=0.5 (the region's left edge).
    bbox = (0.4, 0.0, 0.6, 1.0)  # bottom_center anchor -> (0.5, 1.0)

    hits, _ = evaluate_regions([_detection(bbox, bbox_normalized=True)], [region])

    assert len(hits) == 1


def test_polygon_region_nonconvex():
    """An L-shaped polygon; a point in the notch is excluded."""
    l_shape = NormalizedRegion(
        id="l_shape",
        name="L Shape",
        points=(
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 0.5),
            (0.5, 0.5),
            (0.5, 1.0),
            (0.0, 1.0),
        ),
    )

    # Point in the notch (bottom-right quadrant, cut out of the L).
    notch_bbox = (0.7, 0.6, 0.9, 0.8)
    notch_hits, _ = evaluate_regions(
        [_detection(notch_bbox, bbox_normalized=True)], [l_shape], anchor="center"
    )
    assert len(notch_hits) == 0

    # Point in the filled top-right arm of the L.
    arm_bbox = (0.7, 0.1, 0.9, 0.3)
    arm_hits, _ = evaluate_regions(
        [_detection(arm_bbox, bbox_normalized=True)], [l_shape], anchor="center"
    )
    assert len(arm_hits) == 1


# ---------------------------------------------------------------------------
# Overlap mode
# ---------------------------------------------------------------------------


def test_overlap_mode_threshold():
    """49% overlap misses at the 0.5 default threshold; 51% hits."""
    region = _rect_region(x=0.5, y=0.0, width=0.5, height=1.0)  # right half

    # bbox spans x in [0.0, 0.98]: overlap with region ([0.5,1.0]) is
    # (0.98-0.5)/0.98 = ~0.49 of the bbox area.
    just_under = (0.0, 0.0, 0.98, 1.0)
    hits_under, _ = evaluate_regions(
        [_detection(just_under, bbox_normalized=True)], [region], mode="overlap"
    )
    assert len(hits_under) == 0

    # bbox spans x in [0.0, 0.90]: overlap is (0.90-0.5)/0.90 = ~0.44... use a
    # value that clears 0.5: bbox x in [0.0, 0.9] with region [0.45, 1.0].
    region_51 = _rect_region(region_id="r51", x=0.45, y=0.0, width=0.55, height=1.0)
    just_over = (0.0, 0.0, 0.9, 1.0)
    hits_over, _ = evaluate_regions(
        [_detection(just_over, bbox_normalized=True)], [region_51], mode="overlap"
    )
    assert len(hits_over) == 1


# ---------------------------------------------------------------------------
# Label / confidence filters
# ---------------------------------------------------------------------------


def test_label_and_confidence_filters():
    region = _rect_region(x=0.0, y=0.0, width=1.0, height=1.0)
    detections = [
        _detection((0.1, 0.1, 0.2, 0.2), label="dog", confidence=0.99, bbox_normalized=True),
        _detection((0.1, 0.1, 0.2, 0.2), label="person", confidence=0.2, bbox_normalized=True),
        _detection((0.1, 0.1, 0.2, 0.2), label="Person", confidence=0.9, bbox_normalized=True),
    ]

    hits, _ = evaluate_regions(detections, [region], labels=["person"], min_confidence=0.5)

    assert len(hits) == 1
    assert hits[0].detection_index == 2


# ---------------------------------------------------------------------------
# Bbox space handling
# ---------------------------------------------------------------------------


def test_bbox_space_handling_normalized_passthrough():
    region = _rect_region(x=0.0, y=0.0, width=1.0, height=1.0)
    det = _detection((0.1, 0.1, 0.2, 0.2), bbox_normalized=True)

    hits, skipped = evaluate_regions([det], [region])

    assert len(hits) == 1
    assert skipped == []


def test_bbox_space_handling_pixel_with_dims_normalizes():
    region = _rect_region(x=0.0, y=0.0, width=1.0, height=1.0)
    # Pixel bbox in a 1000x500 image, occupying the top-left quadrant.
    det = _detection((100.0, 50.0, 200.0, 150.0), image_width=1000, image_height=500)

    hits, skipped = evaluate_regions([det], [region])

    assert len(hits) == 1
    assert skipped == []


def test_bbox_space_handling_pixel_without_dims_skips():
    region = _rect_region(x=0.0, y=0.0, width=1.0, height=1.0)
    det = _detection((100.0, 50.0, 200.0, 150.0))  # no bbox_normalized, no dims

    hits, skipped = evaluate_regions([det], [region])

    assert hits == []
    assert skipped == [{"reason": "unknown_bbox_space", "detection_index": 0}]


def test_invalid_bbox_shape_is_skipped():
    region = _rect_region(x=0.0, y=0.0, width=1.0, height=1.0)
    det = _detection([0.1, 0.1], bbox_normalized=True)  # wrong length

    hits, skipped = evaluate_regions([det], [region])

    assert hits == []
    assert skipped == [{"reason": "invalid_bbox", "detection_index": 0}]


# ---------------------------------------------------------------------------
# Camera attribution helper
# ---------------------------------------------------------------------------


def test_detection_camera_id_checks_known_aliases():
    assert detection_camera_id({"camera_id": "cam1"}) == "cam1"
    assert detection_camera_id({"sensor_id": "sensor1"}) == "sensor1"
    assert detection_camera_id({"source_camera_id": "cam2"}) == "cam2"
    assert detection_camera_id({"source_sensor_id": "sensor2"}) == "sensor2"
    assert detection_camera_id({}) is None
