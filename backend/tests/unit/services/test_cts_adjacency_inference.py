"""Unit tests for the adjacency inference service."""

from __future__ import annotations

from backend.services.cts_adjacency_inference import (
    OVERLAP_TRANSIT_MAX_S,
    OVERLAP_TRANSIT_MIN_S,
    infer_adjacency,
)


def _cam(cid: str, polygon: list | None) -> dict:
    return {"id": cid, "visibility_polygon": polygon}


def test_two_fully_overlapping_cameras_produce_overlap_edge():
    poly = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]
    result = infer_adjacency([_cam("a", poly), _cam("b", poly)])
    overlap_edges = [e for e in result.edges if e.overlap]
    assert len(overlap_edges) == 2
    assert abs(overlap_edges[0].iou - 1.0) < 0.01


def test_non_overlapping_nearby_cameras_produce_adjacent_edge():
    poly_a = [[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]]
    poly_b = [[0.3, 0.0], [0.5, 0.0], [0.5, 0.2], [0.3, 0.2]]
    result = infer_adjacency([_cam("a", poly_a), _cam("b", poly_b)])
    adj_edges = [e for e in result.edges if not e.overlap]
    assert len(adj_edges) == 2


def test_far_apart_cameras_produce_no_edge():
    poly_a = [[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]]
    poly_b = [[0.9, 0.9], [1.0, 0.9], [1.0, 1.0], [0.9, 1.0]]
    result = infer_adjacency([_cam("a", poly_a), _cam("b", poly_b)])
    assert len(result.edges) == 0


def test_camera_without_polygon_is_skipped():
    poly = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]
    result = infer_adjacency([_cam("has-poly", poly), _cam("no-poly", None)])
    assert "no-poly" in result.skipped_camera_ids
    assert "has-poly" not in result.skipped_camera_ids


def test_overlap_group_formed_for_overlapping_cameras():
    poly = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]
    result = infer_adjacency([_cam("a", poly), _cam("b", poly), _cam("c", poly)])
    assert len(result.overlap_groups) == 1
    assert sorted(result.overlap_groups[0].camera_ids) == ["a", "b", "c"]


def test_bidirectional_edges_for_all_pairs():
    poly = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]
    result = infer_adjacency([_cam("a", poly), _cam("b", poly)])
    froms = {e.from_camera for e in result.edges}
    tos = {e.to_camera for e in result.edges}
    assert "a" in froms
    assert "b" in froms
    assert "a" in tos
    assert "b" in tos


def test_degenerate_polygon_handled_gracefully():
    result = infer_adjacency([_cam("bad", [[0, 0], [1, 1]])])
    assert "bad" in result.skipped_camera_ids


def test_overlap_transit_bounds():
    poly = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]
    result = infer_adjacency([_cam("a", poly), _cam("b", poly)])
    for e in result.edges:
        assert e.min_transit_s == OVERLAP_TRANSIT_MIN_S
        assert e.max_transit_s == OVERLAP_TRANSIT_MAX_S
