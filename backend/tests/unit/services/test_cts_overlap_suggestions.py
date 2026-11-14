"""Unit tests for overlap-group suggestions from visibility polygons."""

from __future__ import annotations

from backend.services.cts_overlap_suggestions import suggest_overlap_groups

_SQUARE = [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]


def _cam(cid: str, polygon: list | None) -> dict:
    return {"id": cid, "visibility_polygon": polygon}


def test_overlapping_cameras_form_one_group():
    result = suggest_overlap_groups([_cam("b", _SQUARE), _cam("a", _SQUARE), _cam("c", _SQUARE)])
    assert [g.camera_ids for g in result.groups] == [["a", "b", "c"]]
    assert abs(result.groups[0].iou - 1.0) < 0.01


def test_chained_overlap_joins_one_group():
    left = [[0.0, 0.0], [0.4, 0.0], [0.4, 0.4], [0.0, 0.4]]
    middle = [[0.3, 0.0], [0.7, 0.0], [0.7, 0.4], [0.3, 0.4]]
    right = [[0.6, 0.0], [1.0, 0.0], [1.0, 0.4], [0.6, 0.4]]
    result = suggest_overlap_groups([_cam("l", left), _cam("m", middle), _cam("r", right)])
    assert [g.camera_ids for g in result.groups] == [["l", "m", "r"]]


def test_neighbouring_cameras_without_shared_floor_are_not_grouped():
    poly_a = [[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]]
    poly_b = [[0.3, 0.0], [0.5, 0.0], [0.5, 0.2], [0.3, 0.2]]
    assert suggest_overlap_groups([_cam("a", poly_a), _cam("b", poly_b)]).groups == []


def test_camera_without_polygon_is_skipped():
    result = suggest_overlap_groups([_cam("has-poly", _SQUARE), _cam("no-poly", None)])
    assert result.skipped_camera_ids == ["no-poly"]
    assert result.groups == []


def test_degenerate_polygon_is_skipped():
    assert suggest_overlap_groups([_cam("bad", [[0, 0], [1, 1]])]).skipped_camera_ids == ["bad"]
