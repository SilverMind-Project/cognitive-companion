"""Tests for wearable teaching revocation BFF, ReID expired state, and wearable_learners readiness."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.auth import AuthContext
from backend.routers import cts_reid_review as reid_router_mod
from backend.routers import wearables as wearables_router_mod
from backend.schemas.identity_readiness import (
    CTSGalleryCounts,
    CTSIdentityReadiness,
    CTSWearableLearnersReadiness,
)
from backend.services.cts.reid_review_service import ReIDReviewService
from backend.services.identity_readiness_rules import SourceFailure, wearable_learners_step
from backend.services.identity_review.vocabulary import vocabulary_envelope
from backend.services.wearables.teaching_revocation_service import (
    WearableTeachingRevocationService,
)

_T0 = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)


def _cts_readiness(
    *,
    wearable_mode: str = "enabled",
    seeding: bool = True,
    face_attestation: str = "off",
    backfill: bool = False,
    sample_rate: float = 0.2,
    eval_days: int = 5,
    attr_diff: float | None = 0.15,
    open_holds: int = 0,
    revoked_14d: int = 0,
    pending_taught: int = 0,
) -> CTSIdentityReadiness:
    return CTSIdentityReadiness(
        face_evidence_policy="calibrated",
        face_templates_mode="enabled",
        face_quality_mode="enabled",
        cc_assertion_mode="enabled",
        wearable_mode=wearable_mode,
        expected_recognizer_version="buffalo_l",
        expected_quality_version="heuristic-v1",
        reid_gallery_counts=CTSGalleryCounts(
            pending_review=pending_taught,
            auto_verified=2,
            operator_verified=1,
            rejected=0,
            expired=1,
        ),
        wearable_gallery_counts=CTSGalleryCounts(
            pending_review=pending_taught,
            auto_verified=2,
            operator_verified=0,
            rejected=0,
            expired=0,
        ),
        wearable_learners=CTSWearableLearnersReadiness(
            wearable_mode=wearable_mode,
            wearable_seeding_enabled=seeding,
            face_attestation_mode=face_attestation,
            wearable_backfill_enabled=backfill,
            auto_on_swap=True,
            evaluation_sample_rate=sample_rate,
            evaluation_days_14d=eval_days,
            attribution_difference_14d=attr_diff,
            open_teaching_holds=open_holds,
            revoked_segments_14d=revoked_14d,
        ),
        cameras=[],
        overlap_group_count=1,
        identities_known=2,
    )


def test_wearable_learners_readiness_rules() -> None:
    assert wearable_learners_step(SourceFailure("cts")).state == "unknown"

    off = wearable_learners_step(_cts_readiness(wearable_mode="off"))
    assert off.state == "blocked"
    assert off.optional is True

    held = wearable_learners_step(_cts_readiness(open_holds=1))
    assert held.state == "attention"
    assert held.next_action == "resume_wearable_teaching"

    no_sample = wearable_learners_step(_cts_readiness(sample_rate=0.0))
    assert no_sample.state == "attention"
    assert no_sample.next_action == "enable_wearable_learners"

    shadow_pending = wearable_learners_step(
        _cts_readiness(wearable_mode="shadow", seeding=True, pending_taught=3)
    )
    assert shadow_pending.state == "attention"
    assert shadow_pending.next_action == "review_body_samples"

    no_learners = wearable_learners_step(_cts_readiness(seeding=False))
    assert no_learners.state == "attention"
    assert no_learners.next_action == "enable_wearable_learners"

    no_days = wearable_learners_step(_cts_readiness(eval_days=0, attr_diff=None))
    assert no_days.state == "attention"
    assert no_days.next_action == "review_shadow"

    non_positive = wearable_learners_step(_cts_readiness(eval_days=4, attr_diff=0.0))
    assert non_positive.state == "attention"
    assert non_positive.next_action == "review_body_samples"

    ready = wearable_learners_step(_cts_readiness(eval_days=7, attr_diff=0.22, revoked_14d=1))
    assert ready.state == "ready"
    assert ready.next_action == "none"
    assert ready.optional is True


@pytest.mark.asyncio
async def test_reid_review_service_expired_skips_presign_and_reports_expired_count() -> None:
    client = MagicMock()
    client.get_review_counts = AsyncMock(
        return_value={
            "pending_review": 1,
            "auto_verified": 2,
            "operator_verified": 3,
            "rejected": 4,
            "expired": 5,
        }
    )
    client.list_review_candidates = AsyncMock(
        return_value={
            "candidates": [
                {
                    "candidate_id": "c-exp",
                    "state": "expired",
                    "orientation": 0,
                    "quality": 0.9,
                    "is_truncated": False,
                    "is_occluded": False,
                    "audit_version": 2,
                    "crop_key": "reid/c-exp.jpg",
                    "source_frame_key": "frames/c-exp.jpg",
                }
            ],
            "total": 1,
            "limit": 50,
            "offset": 0,
        }
    )
    svc = ReIDReviewService(client)
    counts = await svc.counts()
    assert counts.expired == 5

    presigned: list[str | None] = []
    listed = await svc.list_candidates(
        params={"state": "expired"},
        presign=lambda k: (presigned.append(k), f"https://minio/{k}")[1],
    )
    assert listed.candidates[0].state == "expired"
    assert listed.candidates[0].crop_url is None
    assert listed.candidates[0].frame_url is None
    assert presigned == []


def test_vocabulary_includes_wearable_revocation_effect() -> None:
    env = vocabulary_envelope()
    assert "pending review" in env.wearable_revocation_effect
    assert "resume" in env.wearable_revocation_effect


@pytest.mark.asyncio
async def test_wearable_teaching_revocation_service_merges_taught_and_revokes() -> None:
    device_id = uuid.uuid4()
    fake_device = MagicMock(id=device_id, tag_id="tag-1")
    fake_db = MagicMock()
    fake_db.__enter__.return_value = fake_db
    fake_db.__exit__.return_value = None
    repo = MagicMock()
    repo.session.return_value = fake_db
    repo.get_device.return_value = fake_device

    orchestrator = MagicMock()
    orchestrator.list_wearable_associations = AsyncMock(
        return_value=[
            {
                "segment_id": "seg-1",
                "ph_id": "ph-1",
                "tag_id": "tag-1",
                "identity_id": "alice",
                "started_at": _T0.isoformat(),
                "ended_at": _T0.isoformat(),
                "attestation_grade": "trajectory",
                "swap_suspected": False,
            }
        ]
    )
    orchestrator.list_wearable_holds = AsyncMock(
        return_value=[
            {
                "hold_id": "h-1",
                "tag_id": "tag-1",
                "reason": "operator",
                "held_at": _T0.isoformat(),
                "cleared_at": None,
                "cleared_by": None,
            }
        ]
    )
    orchestrator.get_wearable_association_taught = AsyncMock(
        return_value={
            "segment_id": "seg-1",
            "tag_id": "tag-1",
            "gallery_rows_by_state": {"pending_review": 2},
            "gallery_rows_total": 2,
            "attested_faces_total": 1,
            "attested_faces_active": 0,
            "attested_faces_revoked": 1,
            "attested_faces_promoted": 0,
            "inferred_ranges_live": 0,
            "inferred_ranges_total": 1,
            "tag_teaching_held": True,
        }
    )
    orchestrator.revoke_wearable_association = AsyncMock(
        return_value={
            "segment_id": "seg-1",
            "tag_id": "tag-1",
            "reason": "operator",
            "actor": "api_key:Caregiver Admin",
            "already_revoked": False,
            "gallery_rows_demoted": 2,
            "attested_faces_revoked": 1,
            "already_promoted_faces": [],
            "inferred_ranges_compensated": 1,
            "hold": {
                "hold_id": "h-1",
                "tag_id": "tag-1",
                "reason": "operator",
                "held_at": _T0.isoformat(),
            },
        }
    )
    orchestrator.resume_wearable_tag_teaching = AsyncMock(
        return_value={
            "tag_id": "tag-1",
            "resumed": True,
            "hold": {
                "hold_id": "h-1",
                "tag_id": "tag-1",
                "reason": "operator",
                "held_at": _T0.isoformat(),
                "cleared_at": _T0.isoformat(),
                "cleared_by": "api_key:Caregiver Admin",
            },
        }
    )

    svc = WearableTeachingRevocationService(repo, orchestrator)
    listed = await svc.list_device_associations(device_id)
    assert listed.teaching_held is True
    assert listed.associations[0].gallery_rows_total == 2
    assert listed.associations[0].attested_faces_revoked == 1

    revoked = await svc.revoke_association("seg-1", actor="api_key:Caregiver Admin")
    assert revoked.gallery_rows_demoted == 2
    assert revoked.hold.tag_id == "tag-1"

    resumed = await svc.resume_tag_teaching("tag-1", actor="api_key:Caregiver Admin")
    assert resumed.resumed is True


def test_revoke_and_resume_routes_reject_caregiver_403_and_allow_caregiver_admin() -> None:
    from backend.core.auth import _ensure_keystore, get_auth_context
    from backend.core.exceptions import register_exception_handlers
    from backend.routers.dependencies import get_wearable_teaching_revocation_service
    from backend.schemas.wearables import (
        WearableResumeTeachingResponse,
        WearableRevokeResponse,
        WearableTeachingHoldOut,
    )

    ks = _ensure_keystore()
    caregiver_auth = AuthContext(key="k-caregiver", name="Caregiver", roles=["caregiver"])
    admin_auth = AuthContext(key="k-admin", name="Caregiver Admin", roles=["caregiver_admin"])
    assert ks.has_role_token(caregiver_auth, "wearables.teaching:write") is False
    assert ks.has_role_token(admin_auth, "wearables.teaching:write") is True

    fake_reid_svc = MagicMock()
    fake_reid_svc.list_candidates = AsyncMock(
        return_value={"candidates": [], "total": 0, "limit": 50, "offset": 0}
    )
    fake_revoke_svc = MagicMock()
    fake_revoke_svc.revoke_association = AsyncMock(
        return_value=WearableRevokeResponse(
            segment_id="seg-1",
            tag_id="tag-1",
            reason="operator",
            actor="api_key:Caregiver Admin",
            already_revoked=False,
            gallery_rows_demoted=1,
            attested_faces_revoked=0,
            already_promoted_faces=[],
            inferred_ranges_compensated=0,
            hold=WearableTeachingHoldOut(
                hold_id="h-1", tag_id="tag-1", reason="operator", held_at=_T0
            ),
        )
    )
    fake_revoke_svc.resume_tag_teaching = AsyncMock(
        return_value=WearableResumeTeachingResponse(
            tag_id="tag-1",
            resumed=True,
            hold=WearableTeachingHoldOut(
                hold_id="h-1",
                tag_id="tag-1",
                reason="operator",
                held_at=_T0,
                cleared_at=_T0,
                cleared_by="api_key:Caregiver Admin",
            ),
        )
    )

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(reid_router_mod.router, prefix="/api/v1")
    app.include_router(wearables_router_mod.router, prefix="/api/v1")
    app.dependency_overrides[reid_router_mod.get_reid_review_service] = lambda: fake_reid_svc
    app.dependency_overrides[get_wearable_teaching_revocation_service] = lambda: fake_revoke_svc
    app.state.cts_enabled = True

    # Caregiver gets 403 on both revoke and resume-teaching.
    app.dependency_overrides[get_auth_context] = lambda: caregiver_auth
    client = TestClient(app)
    assert client.post("/api/v1/wearables/associations/seg-1/revoke").status_code == 403
    assert client.post("/api/v1/wearables/tags/tag-1/resume-teaching").status_code == 403

    # Caregiver Admin succeeds with 200 on both, and actor is derived from auth context.
    app.dependency_overrides[get_auth_context] = lambda: admin_auth
    resp_revoke = client.post("/api/v1/wearables/associations/seg-1/revoke")
    assert resp_revoke.status_code == 200
    assert resp_revoke.json()["gallery_rows_demoted"] == 1
    fake_revoke_svc.revoke_association.assert_awaited_once_with("seg-1", actor="Caregiver Admin")

    resp_resume = client.post("/api/v1/wearables/tags/tag-1/resume-teaching")
    assert resp_resume.status_code == 200
    assert resp_resume.json()["resumed"] is True
    fake_revoke_svc.resume_tag_teaching.assert_awaited_once_with("tag-1", actor="Caregiver Admin")

    # ReID review queue forwards seed_association_id and accepts state=expired.
    resp_reid = client.get(
        "/api/v1/cts/identity/reid-review/candidates",
        params={"state": "expired", "seed_association_id": "seg-1"},
    )
    assert resp_reid.status_code == 200
    fake_reid_svc.list_candidates.assert_awaited_once()
    call_args = fake_reid_svc.list_candidates.await_args
    forwarded_params = call_args.args[0] if call_args.args else call_args.kwargs["params"]
    assert forwarded_params["state"] == "expired"
    assert forwarded_params["seed_association_id"] == "seg-1"
