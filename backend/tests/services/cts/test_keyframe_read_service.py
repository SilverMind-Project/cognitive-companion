"""M07: BFF keyframe read service — validation, summary, person_id mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.cts.keyframe_read_service import (
    KeyframeReadContractError,
    KeyframeReadService,
)


def _frame(bboxes: list[dict], **overrides) -> dict:
    frame = {
        "physical_frame_id": "pf-1",
        "camera_id": "cam-a",
        "minio_key": "frames/cam-a/0001-0.jpg",
        "captured_at": "2026-06-19T12:00:00+00:00",
        "frame_width": 1920,
        "frame_height": 1080,
        "triggers": [
            {"keyframe_id": "kf-1", "ph_id": "ph-a", "tag_reason": "periodic"}
        ],
        "trigger_reasons": ["periodic"],
        "unknown_count": 0,
        "conflict_count": 0,
        "pending_review_count": 0,
        "bboxes": bboxes,
    }
    frame.update(overrides)
    return frame


def _bbox(ph_id: str, eff: str | None, **overrides) -> dict:
    bbox = {
        "ph_id": ph_id,
        "x1": 1.0,
        "y1": 2.0,
        "x2": 3.0,
        "y2": 4.0,
        "detection_confidence": 0.9,
        "frame_width": 1920,
        "frame_height": 1080,
        "inferred_identity_id": eff,
        "effective_identity_id": eff,
        "authority": "arcface_authority",
        "decision_source": "face",
        "calibrated_confidence": 0.8,
        "conflict": False,
        "conflict_kind": None,
        "revision_id": None,
        "pending_review": False,
    }
    bbox.update(overrides)
    return bbox


def _service(page: dict) -> KeyframeReadService:
    client = MagicMock()
    client.list_keyframe_frames = AsyncMock(return_value=page)
    return KeyframeReadService(client)


async def test_summary_groups_by_effective_identity_and_maps_person_id() -> None:
    page = {
        "total": 1,
        "frames": [_frame([_bbox("ph-a", "amma"), _bbox("ph-b", "grandma")])],
    }
    result = await _service(page).list_frames()

    card = result.keyframes[0]
    summary = {item.effective_identity_id: item for item in card.identity_summary}
    assert set(summary) == {"amma", "grandma"}
    assert summary["amma"].person_id == "amma"
    assert summary["amma"].count == 1
    # Effective identity surfaces as person_id on every bbox too.
    assert {b.person_id for b in card.bboxes} == {"amma", "grandma"}


async def test_duplicate_identity_increments_count() -> None:
    page = {
        "total": 1,
        "frames": [_frame([_bbox("ph-a", "amma"), _bbox("ph-b", "amma")])],
    }
    result = await _service(page).list_frames()
    summary = result.keyframes[0].identity_summary
    assert len(summary) == 1
    assert summary[0].count == 2


async def test_operator_badge_and_conflict_badge() -> None:
    page = {
        "total": 1,
        "frames": [
            _frame(
                [
                    _bbox("ph-a", "amma", authority="operator", decision_source="operator"),
                    _bbox(
                        "ph-b",
                        "grandma",
                        conflict=True,
                        conflict_kind="duplicate_active",
                    ),
                ]
            )
        ],
    }
    result = await _service(page).list_frames()
    summary = {i.effective_identity_id: i for i in result.keyframes[0].identity_summary}
    assert summary["amma"].source_badges == ["Operator"]
    assert summary["grandma"].source_badges == ["Conflict"]


async def test_malformed_upstream_raises_contract_error() -> None:
    # Missing required 'authority' field on the bbox.
    bad_bbox = _bbox("ph-a", "amma")
    del bad_bbox["authority"]
    page = {"total": 1, "frames": [_frame([bad_bbox])]}
    with pytest.raises(KeyframeReadContractError):
        await _service(page).list_frames()


async def test_missing_frames_key_raises_contract_error() -> None:
    with pytest.raises(KeyframeReadContractError):
        await _service({"oops": []}).list_frames()


async def test_presigned_url_does_not_affect_grouping() -> None:
    # Grouping happens upstream on the source key; the BFF resolves presigned
    # URLs after the fact (in the router, not the service), so the service
    # output is keyed on physical_frame_id and minio_key regardless of any URL.
    page = {"total": 1, "frames": [_frame([_bbox("ph-a", "amma")])]}
    result = await _service(page).list_frames()
    card = result.keyframes[0]
    assert card.physical_frame_id == "pf-1"
    assert card.minio_key == "frames/cam-a/0001-0.jpg"
    # The service never sets image_url; presigning is a separate router step.
    assert card.image_url is None
