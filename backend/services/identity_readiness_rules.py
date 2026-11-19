"""The identity readiness rules: one pure function per step, from source data to a state.

Each function takes what its sources returned, or a ``SourceFailure`` when a source could not be
read, and decides one ``ReadinessStep``. No I/O happens here, so every rule is tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.integrations.person_id_client import (
    CalibrationHealthInfo,
    CalibrationSummaryInfo,
    MemberInfo,
)
from backend.schemas.identity_readiness import (
    CTSIdentityReadiness,
    ReadinessNextAction,
    ReadinessState,
    ReadinessStep,
    ReadinessStepKey,
    ReviewQueue,
)
from backend.schemas.identity_roster import RosterHealthEnvelope

# A camera that has not delivered a frame for this long is not feeding identity at all.
STALE_FRAME_S = 60.0
# A camera with this role is an identification point, not a tracking camera: it needs no
# floor homography for the floor frame to be complete.
FACE_ONLY_ROLE = "face_capable"
ARTIFACT_READY = "ready"
ARTIFACT_MISSING = "degraded_missing"

_ROSTER_SCOPE = (
    "Roster health can only check people listed under People: the person you care for must be "
    "listed and enrolled there, or nothing here can notice they are missing."
)


def _count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


@dataclass(frozen=True)
class SourceFailure:
    """A source that could not be read; its steps report ``unknown``."""

    source: str


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str
    role: str
    has_homography: bool


@dataclass(frozen=True)
class HouseholdFloorFrame:
    has_floor_plan: bool
    has_scale: bool
    room_count: int
    rooms_with_polygon: int
    cameras: tuple[CameraConfig, ...]
    overlap_group_count: int


@dataclass(frozen=True)
class IngestHealth:
    """Per enabled camera, seconds since its last frame; None when ingress could not say."""

    frame_age_s: dict[str, float | None]


def _unknown(
    key: ReadinessStepKey, failure: SourceFailure, *, optional: bool = False
) -> ReadinessStep:
    return ReadinessStep(
        key=key,
        state="unknown",
        detail=f"Could not read {failure.source}; check that it is running.",
        next_action="check_service",
        optional=optional,
    )


def _clusters(n: int) -> str:
    return (
        f"{_count(n, 'group')} of recurring unrecognized faces "
        f"{'is' if n == 1 else 'are'} waiting for review. Many are usually faces of someone "
        "already enrolled: mark those as theirs, name only someone new, and dismiss the rest."
    )


_POSE_BINS = ("frontal", "left", "right", "down")


def _prototype_counts_detail(members: list[MemberInfo] | SourceFailure | None) -> str:
    if not isinstance(members, list) or not members:
        return ""
    totals: dict[str, int] = dict.fromkeys(_POSE_BINS, 0)
    has_any = False
    for member in members:
        for pose_bin, count in (member.prototype_counts or {}).items():
            if count > 0:
                has_any = True
                totals[pose_bin] = totals.get(pose_bin, 0) + int(count)
    if not has_any:
        return ""
    ordered = list(_POSE_BINS) + sorted(b for b in totals if b not in _POSE_BINS)
    parts = [f"{totals[b]} {b}" for b in ordered]
    return f"Face prototypes across enrolled members: {', '.join(parts)}. "


def roster_step(
    roster: RosterHealthEnvelope | SourceFailure,
    members: list[MemberInfo] | SourceFailure | None = None,
) -> ReadinessStep:
    if isinstance(roster, SourceFailure):
        return _unknown("roster", roster)
    missing = len(roster.members_without_face_enrollment)
    clusters = roster.surfaced_unnamed_visitor_clusters
    prototypes = _prototype_counts_detail(members)
    if roster.active_member_count == 0:
        return ReadinessStep(
            key="roster",
            state="blocked",
            detail=(
                "Nobody is listed. List and enroll every person who lives in the house. "
                + _ROSTER_SCOPE
            ),
            next_action="enroll_members",
        )
    if missing:
        return ReadinessStep(
            key="roster",
            state="attention",
            detail=(
                f"{missing} of {_count(roster.active_member_count, 'member')} "
                f"{'has' if missing == 1 else 'have'} fewer than "
                f"{roster.min_face_embeddings} enrolled face photos. "
                + (_clusters(clusters) + " " if clusters else "")
                + prototypes
                + _ROSTER_SCOPE
            ),
            next_action="enroll_members",
        )
    if clusters:
        return ReadinessStep(
            key="roster",
            state="attention",
            detail=f"{_clusters(clusters)} {prototypes}{_ROSTER_SCOPE}",
            next_action="review_visitors",
        )
    everyone = (
        "The one member is"
        if roster.active_member_count == 1
        else f"All {roster.active_member_count} members are"
    )
    return ReadinessStep(
        key="roster",
        state="ready",
        detail=f"{everyone} enrolled. {prototypes}{_ROSTER_SCOPE}",
        next_action="none",
    )


def ingest_step(ingest: IngestHealth | SourceFailure) -> ReadinessStep:
    if isinstance(ingest, SourceFailure):
        return _unknown("ingest", ingest)
    ages = ingest.frame_age_s
    if not ages:
        return ReadinessStep(
            key="ingest",
            state="blocked",
            detail="No camera is enabled.",
            next_action="fix_camera_ingest",
        )
    stale = sorted(cid for cid, age in ages.items() if age is not None and age > STALE_FRAME_S)
    unread = sorted(cid for cid, age in ages.items() if age is None)
    if stale:
        return ReadinessStep(
            key="ingest",
            state="attention",
            detail=f"No frame for over {STALE_FRAME_S:.0f} s from: {', '.join(stale)}.",
            next_action="fix_camera_ingest",
        )
    if unread:
        return ReadinessStep(
            key="ingest",
            state="unknown",
            detail=f"Frame age unavailable for: {', '.join(unread)}.",
            next_action="check_service",
        )
    return ReadinessStep(
        key="ingest",
        state="ready",
        detail=f"All {len(ages)} enabled cameras delivered a frame in the last minute.",
        next_action="none",
    )


def floor_frame_step(
    household: HouseholdFloorFrame, cts: CTSIdentityReadiness | SourceFailure
) -> ReadinessStep:
    groups = f"{_count(household.overlap_group_count, 'overlap group')}."
    if not (household.has_floor_plan and household.has_scale):
        return ReadinessStep(
            key="floor_frame",
            state="blocked",
            detail="No floor plan with a measured scale; people cannot be placed on the floor. "
            + groups,
            next_action="upload_floor_plan",
        )
    if household.room_count == 0 or household.rooms_with_polygon < household.room_count:
        return ReadinessStep(
            key="floor_frame",
            state="attention",
            detail=(
                "No rooms are defined. "
                if household.room_count == 0
                else f"{household.rooms_with_polygon} of {household.room_count} rooms have a "
                "polygon on the floor plan. "
            )
            + groups,
            next_action="draw_room_polygons",
        )
    tracking = [c for c in household.cameras if c.role != FACE_ONLY_ROLE]
    uncalibrated = sorted(c.camera_id for c in tracking if not c.has_homography)
    if uncalibrated:
        return ReadinessStep(
            key="floor_frame",
            state="attention",
            detail=(
                "Floor plan and rooms are set; cameras without a floor calibration: "
                f"{', '.join(uncalibrated)}. " + groups
            ),
            next_action="calibrate_cameras",
        )
    if isinstance(cts, SourceFailure):
        return _unknown("floor_frame", cts)
    in_use = {c.camera_id for c in cts.cameras if c.calibrated}
    not_applied = sorted(
        c.camera_id for c in tracking if c.has_homography and c.camera_id not in in_use
    )
    if not_applied:
        return ReadinessStep(
            key="floor_frame",
            state="attention",
            detail=(
                "Calibrated here but not in use by tracking (rejected or not yet synced): "
                f"{', '.join(not_applied)}. " + groups
            ),
            next_action="calibrate_cameras",
        )
    return ReadinessStep(
        key="floor_frame",
        state="ready",
        detail=f"Every tracking camera is calibrated and in use. {groups}",
        next_action="none",
    )


def _targets_met(summary: CalibrationSummaryInfo) -> bool:
    return bool(summary.identities) and all(
        i.labeled_faces >= i.target_labeled_faces for i in summary.identities
    )


def capture_step(
    summary: CalibrationSummaryInfo | SourceFailure,
    health: CalibrationHealthInfo | SourceFailure,
) -> ReadinessStep:
    if isinstance(summary, SourceFailure):
        return _unknown("capture", summary)
    if _targets_met(summary):
        return ReadinessStep(
            key="capture",
            state="ready",
            detail="Every enrolled person has enough labeled faces.",
            next_action="none",
        )
    if summary.capture_enabled:
        return ReadinessStep(
            key="capture",
            state="attention",
            detail="Capture is on; faces are being collected for labeling.",
            next_action="label_captures",
        )
    if isinstance(health, SourceFailure):
        return _unknown("capture", health)
    if health.status == ARTIFACT_READY:
        return ReadinessStep(
            key="capture",
            state="ready",
            detail="Capture is off and a calibration artifact is deployed.",
            next_action="none",
        )
    return ReadinessStep(
        key="capture",
        state="blocked",
        detail="Capture is off and no calibration artifact exists, so nothing can be labeled.",
        next_action="enable_capture",
    )


def labeling_step(summary: CalibrationSummaryInfo | SourceFailure) -> ReadinessStep:
    if isinstance(summary, SourceFailure):
        return _unknown("labeling", summary)
    unlabeled = summary.by_state.get("unlabeled", 0)
    labeled = summary.by_state.get("labeled", 0)
    at_target = sum(1 for i in summary.identities if i.labeled_faces >= i.target_labeled_faces)
    progress = (
        f"{at_target} of {len(summary.identities)} people at target; {labeled} faces labeled, "
        f"{unlabeled} waiting; {summary.not_enrolled_episodes} visitor walks labeled."
    )
    if _targets_met(summary):
        return ReadinessStep(key="labeling", state="ready", detail=progress, next_action="none")
    if unlabeled == 0 and labeled == 0:
        return ReadinessStep(
            key="labeling",
            state="blocked",
            detail="Nothing has been captured to label yet.",
            next_action="enable_capture" if not summary.capture_enabled else "label_captures",
        )
    return ReadinessStep(
        key="labeling", state="attention", detail=progress, next_action="label_captures"
    )


def artifact_step(
    health: CalibrationHealthInfo | SourceFailure,
    members: list[MemberInfo] | SourceFailure,
) -> ReadinessStep:
    if isinstance(health, SourceFailure):
        return _unknown("artifact", health)
    if health.status == ARTIFACT_MISSING:
        return ReadinessStep(
            key="artifact",
            state="blocked",
            detail="No face calibration artifact is deployed; face scores are uncalibrated.",
            next_action="fit_and_deploy_artifact",
        )
    if health.status != ARTIFACT_READY:
        return ReadinessStep(
            key="artifact",
            state="blocked",
            detail=f"The calibration artifact is not usable (status {health.status}).",
            next_action="fit_and_deploy_artifact",
        )
    if isinstance(members, SourceFailure):
        return _unknown("artifact", members)
    covered = set(health.covered_identities or [])
    uncovered = sum(1 for m in members if m.person_id not in covered)
    if uncovered:
        return ReadinessStep(
            key="artifact",
            state="attention",
            detail=(
                f"{_count(uncovered, 'member')} enrolled after the artifact was fitted "
                f"{'gets' if uncovered == 1 else 'get'} no calibrated confidence until it is "
                "refitted."
            ),
            next_action="refit_artifact",
        )
    return ReadinessStep(
        key="artifact",
        state="ready",
        detail=f"Deployed and covering all {len(members)} enrolled members.",
        next_action="none",
    )


def face_policy_step(
    cts: CTSIdentityReadiness | SourceFailure, artifact_ready: bool
) -> ReadinessStep:
    if isinstance(cts, SourceFailure):
        return _unknown("face_policy", cts)
    policy = cts.face_evidence_policy
    if policy == "calibrated":
        return ReadinessStep(
            key="face_policy",
            state="ready",
            detail="Calibrated face evidence is live.",
            next_action="none",
        )
    if policy == "shadow":
        return ReadinessStep(
            key="face_policy",
            state="attention",
            detail=(
                "Calibrated face evidence runs in shadow; review it, then switch to calibrated."
                if artifact_ready
                else "Shadow mode measures nothing until a calibration artifact is deployed."
            ),
            next_action="review_shadow" if artifact_ready else "fit_and_deploy_artifact",
        )
    return ReadinessStep(
        key="face_policy",
        state="blocked",
        detail=f"Face evidence policy is {policy}: calibrated faces are not used.",
        next_action="review_shadow",
    )


def templates_step(
    cts: CTSIdentityReadiness | SourceFailure,
    health: CalibrationHealthInfo | SourceFailure,
) -> ReadinessStep:
    if isinstance(cts, SourceFailure):
        return _unknown("templates", cts, optional=True)
    if isinstance(health, SourceFailure):
        return _unknown("templates", health, optional=True)
    mode = cts.face_templates_mode
    state: ReadinessState
    action: ReadinessNextAction
    if mode == "enabled" and health.template_status == ARTIFACT_READY:
        state, action = "ready", "none"
        detail = "Face templates are live."
    elif mode == "shadow":
        state, action = "attention", "review_shadow"
        detail = "Face templates run in shadow."
    elif health.template_status != ARTIFACT_READY:
        state, action = "blocked", "fit_and_deploy_artifact"
        detail = (
            f"Face templates are {mode}; they need their own calibration artifact first."
            if mode == "off"
            else f"Face templates are {mode} but their calibration artifact is not deployed."
        )
    else:
        state, action = "attention", "enable_templates"
        detail = f"A template artifact is deployed; templates are {mode}."
    return ReadinessStep(
        key="templates",
        state=state,
        detail=detail + " Templates are an optional improvement after calibrated faces are live.",
        next_action=action,
        optional=True,
    )


def body_gallery_step(cts: CTSIdentityReadiness | SourceFailure) -> ReadinessStep:
    if isinstance(cts, SourceFailure):
        return _unknown("body_gallery", cts)
    counts = cts.reid_gallery_counts
    if counts is None:
        return ReadinessStep(
            key="body_gallery",
            state="unknown",
            detail="The tracking orchestrator runs without its gallery database.",
            next_action="check_service",
        )
    voting = counts.auto_verified + counts.operator_verified
    summary = (
        f"{voting} voting samples ({counts.operator_verified} operator verified), "
        f"{counts.pending_review} waiting for review, {counts.rejected} rejected."
    )
    if counts.pending_review:
        return ReadinessStep(
            key="body_gallery",
            state="attention",
            detail=summary,
            next_action="review_body_samples",
        )
    if voting == 0:
        live = cts.face_evidence_policy == "calibrated"
        return ReadinessStep(
            key="body_gallery",
            state="blocked",
            detail=summary
            + (
                " Waiting for calibrated faces to confirm tracked people."
                if live
                else " Samples are proposed only after calibrated face evidence is live."
            ),
            next_action="none" if live else "set_policy_calibrated",
        )
    return ReadinessStep(key="body_gallery", state="ready", detail=summary, next_action="none")


def review_queues(
    roster: RosterHealthEnvelope | SourceFailure,
    summary: CalibrationSummaryInfo | SourceFailure,
    cts: CTSIdentityReadiness | SourceFailure,
) -> list[ReviewQueue]:
    """How much waits on each review surface, from the reads the steps already made."""
    visitors = (
        None if isinstance(roster, SourceFailure) else roster.surfaced_unnamed_visitor_clusters
    )
    captures = None if isinstance(summary, SourceFailure) else summary.by_state.get("unlabeled", 0)
    gallery = None if isinstance(cts, SourceFailure) else cts.reid_gallery_counts
    return [
        ReviewQueue(surface="visitors", waiting=visitors),
        ReviewQueue(surface="face_calibration", waiting=captures),
        ReviewQueue(
            surface="reid_review", waiting=None if gallery is None else gallery.pending_review
        ),
    ]
