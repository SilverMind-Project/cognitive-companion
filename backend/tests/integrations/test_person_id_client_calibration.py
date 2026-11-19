"""PersonIDClient calibration-review methods: request shapes, parsing, and contract failures."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.integrations.person_id_client import PersonIDUpstreamError
from backend.tests.integrations.test_person_id_client_visitors import (
    _HTTPX_TARGET,
    _make_client,
    _mock_http,
)

_CANDIDATE = {
    "candidate_id": "c1",
    "captured_at": "2026-10-21T09:00:00+00:00",
    "camera_id": "cam-1",
    "crop_object_key": "calibration/2026-10-21/c1.png",
    "quality_score": 0.41,
    "quality_version": "heuristic-v1",
    "interocular_px": None,
    "yaw_deg": 3.0,
    "pitch_deg": -2.0,
    "nearest_person_id": "amma",
    "nearest_similarity": -0.05,
    "label_state": "labeled",
    "label_kind": "member",
    "label_identity_id": "amma",
    "labeled_by": "admin",
    "labeled_at": "2026-10-21T10:00:00+00:00",
}


async def test_list_parses_candidates_and_sends_paging_params() -> None:
    client = _make_client()
    mock = _mock_http({"candidates": [_CANDIDATE], "next_cursor": "next"})
    with patch(_HTTPX_TARGET, return_value=mock):
        page = await client.list_calibration_candidates(state="unlabeled", limit=25, cursor="k")
    http = mock.__aenter__.return_value
    args, kwargs = http.request.await_args
    assert args == ("GET", "http://person-id-test/api/v1/calibration/candidates")
    assert kwargs["params"] == {"limit": "25", "state": "unlabeled", "cursor": "k"}
    [candidate] = page.candidates
    assert page.next_cursor == "next"
    assert (candidate.nearest_similarity, candidate.interocular_px) == (-0.05, None)
    assert candidate.labeled_at is not None


async def test_label_sends_the_labeler_and_parses_the_result() -> None:
    client = _make_client()
    mock = _mock_http(_CANDIDATE)
    with patch(_HTTPX_TARGET, return_value=mock):
        result = await client.label_calibration_candidate(
            "c1", label_kind="member", label_identity_id="amma", labeled_by="admin"
        )
    _args, kwargs = mock.__aenter__.return_value.request.await_args
    assert kwargs["json"] == {
        "label_kind": "member",
        "label_identity_id": "amma",
        "labeled_by": "admin",
    }
    assert result.label_identity_id == "amma"


async def test_summary_parses_progress() -> None:
    client = _make_client()
    payload = {
        "by_state": {"unlabeled": 4},
        "by_label_kind": {"member": 2},
        "by_quality_decile": {"3": 2},
        "by_camera": {"cam-1": 2},
        "identities": [
            {"identity_id": "amma", "labeled_faces": 2, "episodes": 1, "target_labeled_faces": 150}
        ],
        "not_enrolled_episodes": 0,
        "capture_enabled": True,
    }
    with patch(_HTTPX_TARGET, return_value=_mock_http(payload)):
        summary = await client.get_calibration_summary()
    assert summary.identities[0].target_labeled_faces == 150
    assert summary.capture_enabled is True


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.list_calibration_candidates(state=None, limit=10, cursor=None),
        lambda c: c.get_calibration_summary(),
        lambda c: c.reject_calibration_candidate("c1"),
        lambda c: c.promote_calibration_candidate("c1", approved_by="admin"),
        lambda c: c.list_member_prototypes("amma"),
        lambda c: c.rebuild_member_prototypes("amma"),
    ],
)
async def test_malformed_envelopes_are_502(call) -> None:
    client = _make_client()
    with (
        patch(_HTTPX_TARGET, return_value=_mock_http({"unexpected": True})),
        pytest.raises(PersonIDUpstreamError) as exc,
    ):
        await call(client)
    assert exc.value.status == 502


async def test_not_found_keeps_its_status() -> None:
    client = _make_client()
    with (
        patch(_HTTPX_TARGET, return_value=_mock_http({"detail": "candidate not found"}, 404)),
        pytest.raises(PersonIDUpstreamError) as exc,
    ):
        await client.delete_calibration_candidate("c1")
    assert exc.value.status == 404


async def test_promote_list_rebuild_and_delete_prototypes() -> None:
    client = _make_client()
    promote_payload = {
        "candidate_id": "c1",
        "person_id": "amma",
        "pose_bin": "down",
        "embedding_id": 42,
        "gallery_revision": 3,
        "prototype_count": 4,
        "counts_by_bin": {"frontal": 2, "down": 2},
    }
    mock_promote = _mock_http(promote_payload)
    with patch(_HTTPX_TARGET, return_value=mock_promote):
        promoted = await client.promote_calibration_candidate("c1", approved_by="admin-tablet")
    assert (promoted.person_id, promoted.pose_bin, promoted.gallery_revision) == ("amma", "down", 3)
    assert mock_promote.__aenter__.return_value.request.await_args.kwargs["json"] == {
        "approved_by": "admin-tablet"
    }

    proto_payload = {
        "person_id": "amma",
        "gallery_revision": 3,
        "prototypes": [
            {
                "prototype_id": "p1",
                "person_id": "amma",
                "pose_bin": "down",
                "member_count": 1,
                "source": "promoted_capture",
                "quality_score": 0.72,
                "quality_version": "heuristic-v1",
                "crop_object_key": "calibration/2026-11-19/c1.png",
                "approved_by": "admin-tablet",
                "approved_at": "2026-11-19T08:00:00+00:00",
                "created_at": "2026-11-19T08:00:00+00:00",
            }
        ],
        "counts_by_bin": {"down": 1},
    }
    with patch(_HTTPX_TARGET, return_value=_mock_http(proto_payload)):
        listed = await client.list_member_prototypes("amma")
    assert listed.gallery_revision == 3
    assert listed.prototypes[0].crop_object_key == "calibration/2026-11-19/c1.png"

    rebuild_payload = {"person_id": "amma", "prototype_count": 2, "counts_by_bin": {"frontal": 2}}
    with patch(_HTTPX_TARGET, return_value=_mock_http(rebuild_payload)):
        rebuilt = await client.rebuild_member_prototypes("amma")
    assert rebuilt.prototype_count == 2

    mock_del = _mock_http(None, 204)
    with patch(_HTTPX_TARGET, return_value=mock_del):
        await client.delete_member_prototype("amma", "p1")
    args, _kwargs = mock_del.__aenter__.return_value.request.await_args
    assert args == ("DELETE", "http://person-id-test/api/v1/members/amma/prototypes/p1")
