"""Each identity readiness rule, from source data to one state and one next action."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.integrations.person_id_client import (
    CalibrationHealthInfo,
    CalibrationIdentityProgress,
    CalibrationSummaryInfo,
    MemberInfo,
)
from backend.schemas.identity_readiness import (
    CTSCameraCalibration,
    CTSGalleryCounts,
    CTSIdentityReadiness,
)
from backend.schemas.identity_roster import RosterHealthEnvelope, RosterMemberRef
from backend.services.identity_readiness_rules import (
    CameraConfig,
    HouseholdFloorFrame,
    IngestHealth,
    SourceFailure,
    artifact_step,
    body_gallery_step,
    capture_step,
    face_policy_step,
    floor_frame_step,
    ingest_step,
    labeling_step,
    roster_step,
    templates_step,
)

_AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
_DOWN = SourceFailure("person identification")


def _roster(*, members: int = 3, missing: int = 0, visitors: int = 0) -> RosterHealthEnvelope:
    return RosterHealthEnvelope(
        members_without_face_enrollment=[
            RosterMemberRef(member_id=f"m{i}", name=f"M{i}", embedding_count=1)
            for i in range(missing)
        ],
        active_member_count=members,
        min_face_embeddings=5,
        visitor_clustering_enabled=True,
        surfaced_unnamed_visitor_clusters=visitors,
        is_complete=missing == 0 and visitors == 0,
        checked_at=_AT,
    )


def _summary(
    *,
    capture: bool = False,
    unlabeled: int = 0,
    labeled: int = 0,
    progress: tuple[int, ...] = (),
) -> CalibrationSummaryInfo:
    return CalibrationSummaryInfo(
        by_state={"unlabeled": unlabeled, "labeled": labeled, "rejected": 0},
        by_label_kind={},
        by_quality_decile={},
        by_camera={},
        identities=[
            CalibrationIdentityProgress(
                identity_id=f"id{i}", labeled_faces=n, episodes=3, target_labeled_faces=100
            )
            for i, n in enumerate(progress)
        ],
        not_enrolled_episodes=0,
        capture_enabled=capture,
    )


def _health(
    status: str = "degraded_missing",
    covered: list[str] | None = None,
    template_status: str = "degraded_missing",
) -> CalibrationHealthInfo:
    return CalibrationHealthInfo(
        status=status, covered_identities=covered, template_status=template_status
    )


def _members(*ids: str) -> list[MemberInfo]:
    return [MemberInfo(person_id=i, name=i, embedding_count=7, created_at=_AT) for i in ids]


def _cts(
    *,
    policy: str = "shadow",
    templates: str = "off",
    counts: CTSGalleryCounts | None = None,
    calibrated: tuple[str, ...] = (),
) -> CTSIdentityReadiness:
    return CTSIdentityReadiness(
        face_evidence_policy=policy,
        face_templates_mode=templates,
        face_quality_mode="shadow",
        cc_assertion_mode="shadow",
        expected_arcface_model_version=None,
        expected_quality_version="heuristic-v1",
        reid_gallery_counts=counts,
        cameras=[CTSCameraCalibration(camera_id=c, calibrated=True) for c in calibrated],
        overlap_group_count=0,
        identities_known=2,
    )


def _floor(
    *,
    plan: bool = True,
    rooms: int = 2,
    polygons: int = 2,
    cameras: tuple[CameraConfig, ...] = (),
) -> HouseholdFloorFrame:
    return HouseholdFloorFrame(
        has_floor_plan=plan,
        has_scale=plan,
        room_count=rooms,
        rooms_with_polygon=polygons,
        cameras=cameras,
        overlap_group_count=1,
    )


# -- roster -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("roster", "state", "action"),
    [
        (_roster(members=1), "blocked", "enroll_members"),
        (_roster(missing=1, visitors=1), "blocked", "enroll_members"),
        (_roster(visitors=2), "blocked", "review_visitors"),
        (_roster(missing=1), "attention", "enroll_members"),
        (_roster(), "ready", "none"),
    ],
)
def test_roster(roster: RosterHealthEnvelope, state: str, action: str) -> None:
    step = roster_step(roster)
    assert (step.state, step.next_action) == (state, action)


def test_roster_always_says_it_cannot_see_unlisted_people() -> None:
    assert "must be listed" in roster_step(_roster()).detail


def test_roster_source_down_is_unknown() -> None:
    step = roster_step(_DOWN)
    assert (step.state, step.next_action) == ("unknown", "check_service")


# -- ingest -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("ages", "state"),
    [
        ({}, "blocked"),
        ({"a": 0.5, "b": 61.0}, "attention"),
        ({"a": 0.5, "b": None}, "unknown"),
        ({"a": 0.5, "b": 59.0}, "ready"),
    ],
)
def test_ingest(ages: dict[str, float | None], state: str) -> None:
    assert ingest_step(IngestHealth(frame_age_s=ages)).state == state


def test_ingest_names_the_silent_camera() -> None:
    step = ingest_step(IngestHealth(frame_age_s={"hall": 120.0, "kitchen": 1.0}))
    assert "hall" in step.detail
    assert "kitchen" not in step.detail


# -- floor frame ------------------------------------------------------------

_TRACKING = CameraConfig(camera_id="hall", role="mixed", has_homography=True)
_FACE_ONLY = CameraConfig(camera_id="door", role="face_capable", has_homography=False)


@pytest.mark.parametrize(
    ("floor", "cts", "state", "action"),
    [
        (_floor(plan=False), _cts(), "blocked", "upload_floor_plan"),
        (_floor(polygons=1), _cts(), "attention", "draw_room_polygons"),
        (
            _floor(cameras=(CameraConfig("hall", "surveillance", False),)),
            _cts(),
            "attention",
            "calibrate_cameras",
        ),
        # Calibrated in CC but CTS rejected or has not synced the homography.
        (_floor(cameras=(_TRACKING,)), _cts(), "attention", "calibrate_cameras"),
        (_floor(cameras=(_TRACKING,)), _DOWN, "unknown", "check_service"),
        # A face-only camera needs no homography.
        (_floor(cameras=(_TRACKING, _FACE_ONLY)), _cts(calibrated=("hall",)), "ready", "none"),
    ],
)
def test_floor_frame(
    floor: HouseholdFloorFrame,
    cts: CTSIdentityReadiness | SourceFailure,
    state: str,
    action: str,
) -> None:
    step = floor_frame_step(floor, cts)
    assert (step.state, step.next_action) == (state, action)


# -- capture and labeling ---------------------------------------------------


@pytest.mark.parametrize(
    ("summary", "health", "state", "action"),
    [
        (_summary(), _health(), "blocked", "enable_capture"),
        (_summary(capture=True), _health(), "attention", "label_captures"),
        (_summary(), _health("ready"), "ready", "none"),
        (_summary(progress=(100, 120)), _health(), "ready", "none"),
        (_summary(), _DOWN, "unknown", "check_service"),
        (_DOWN, _health(), "unknown", "check_service"),
    ],
)
def test_capture(
    summary: CalibrationSummaryInfo | SourceFailure,
    health: CalibrationHealthInfo | SourceFailure,
    state: str,
    action: str,
) -> None:
    step = capture_step(summary, health)
    assert (step.state, step.next_action) == (state, action)


@pytest.mark.parametrize(
    ("summary", "state", "action"),
    [
        (_summary(), "blocked", "enable_capture"),
        (_summary(capture=True), "blocked", "label_captures"),
        (
            _summary(capture=True, unlabeled=40, labeled=10, progress=(10,)),
            "attention",
            "label_captures",
        ),
        (_summary(labeled=220, progress=(100, 120)), "ready", "none"),
        # An empty progress list is never "every target met".
        (_summary(labeled=5, progress=()), "attention", "label_captures"),
    ],
)
def test_labeling(summary: CalibrationSummaryInfo, state: str, action: str) -> None:
    step = labeling_step(summary)
    assert (step.state, step.next_action) == (state, action)


# -- artifact and policies --------------------------------------------------


@pytest.mark.parametrize(
    ("health", "members", "state", "action"),
    [
        (_health(), _members("a"), "blocked", "fit_and_deploy_artifact"),
        (_health("invalid"), _members("a"), "blocked", "fit_and_deploy_artifact"),
        (_health("ready", ["a"]), _members("a", "b"), "attention", "refit_artifact"),
        (_health("ready", ["a", "b"]), _members("a", "b"), "ready", "none"),
        (_health("ready", ["a"]), _DOWN, "unknown", "check_service"),
    ],
)
def test_artifact(
    health: CalibrationHealthInfo,
    members: list[MemberInfo] | SourceFailure,
    state: str,
    action: str,
) -> None:
    step = artifact_step(health, members)
    assert (step.state, step.next_action) == (state, action)


@pytest.mark.parametrize(
    ("policy", "artifact_ready", "state", "action"),
    [
        ("legacy", True, "blocked", "review_shadow"),
        ("shadow", False, "attention", "fit_and_deploy_artifact"),
        ("shadow", True, "attention", "review_shadow"),
        ("calibrated", True, "ready", "none"),
    ],
)
def test_face_policy(policy: str, artifact_ready: bool, state: str, action: str) -> None:
    step = face_policy_step(_cts(policy=policy), artifact_ready)
    assert (step.state, step.next_action) == (state, action)


@pytest.mark.parametrize(
    ("mode", "template_status", "state"),
    [
        ("off", "degraded_missing", "blocked"),
        ("off", "ready", "attention"),
        ("shadow", "ready", "attention"),
        ("enabled", "ready", "ready"),
    ],
)
def test_templates_are_optional(mode: str, template_status: str, state: str) -> None:
    step = templates_step(_cts(templates=mode), _health(template_status=template_status))
    assert step.state == state
    assert step.optional is True


def _counts(pending: int = 0, auto: int = 0, operator: int = 0) -> CTSGalleryCounts:
    return CTSGalleryCounts(
        pending_review=pending, auto_verified=auto, operator_verified=operator, rejected=0
    )


@pytest.mark.parametrize(
    ("cts", "state", "action"),
    [
        (_cts(counts=None), "unknown", "check_service"),
        (_cts(counts=_counts()), "blocked", "set_policy_calibrated"),
        (_cts(policy="calibrated", counts=_counts()), "blocked", "none"),
        (_cts(counts=_counts(pending=3, auto=1)), "attention", "review_body_samples"),
        (_cts(counts=_counts(auto=4, operator=2)), "ready", "none"),
    ],
)
def test_body_gallery(cts: CTSIdentityReadiness, state: str, action: str) -> None:
    step = body_gallery_step(cts)
    assert (step.state, step.next_action) == (state, action)


def test_details_count_in_plain_words() -> None:
    assert roster_step(_roster(members=1)).detail.startswith("1 household member listed")
    assert "2 recurring visitors, seen" in roster_step(_roster(visitors=2)).detail
    assert "1 of 3 members has fewer than" in roster_step(_roster(missing=1)).detail
    assert floor_frame_step(_floor(plan=False), _cts()).detail.endswith("1 overlap group.")
    refit = artifact_step(_health("ready", ["a"]), _members("a", "b")).detail
    assert refit.startswith("1 member enrolled after the artifact was fitted gets no")
