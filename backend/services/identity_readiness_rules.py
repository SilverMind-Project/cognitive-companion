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
# Fixed RF receivers must be heard within this window to count as active on readiness.
RF_NODE_HEARD_WINDOW_S = 300.0
# A camera with this role is an identification point, not a tracking camera: it needs no
# floor homography for the floor frame to be complete.
FACE_ONLY_ROLE = "face_capable"
ARTIFACT_READY = "ready"
ARTIFACT_MISSING = "degraded_missing"
ARTIFACT_INCOMPATIBLE = "degraded_incompatible"

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


@dataclass(frozen=True)
class WearablesHealth:
    """Wearable registry counts, live RF-node/tag freshness, and battery for the wearables step."""

    active_node_count: int
    active_device_count: int
    active_binding_count: int
    low_battery_count: int
    last_heard_age_s: float | None
    nodes_heard_recent_count: int | None = None
    tags_heard_count: int | None = None
    lowest_battery_fraction: float | None = None
    rf_ingress_unreachable: bool = False


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


def _closed_world_detail(cts: CTSIdentityReadiness | SourceFailure | None) -> str:
    if not isinstance(cts, CTSIdentityReadiness) or cts.closed_world is None:
        return ""
    cw = cts.closed_world
    if cw.mode == "off":
        return "Closed-world prior shaping is off. "
    if cw.active:
        if cw.inactive_reason == "presence_stale":
            return (
                f"Closed-world prior shaping is active ({cw.mode}; household presence is stale, "
                "so away penalties are paused). "
            )
        return f"Closed-world prior shaping is active ({cw.mode}). "
    reason_map = {
        "roster_incomplete": "roster incomplete",
        "no_presence": "waiting for household presence stream",
        "no_identities": "no enrolled identities synced",
    }
    reason_text = reason_map.get(cw.inactive_reason or "", cw.inactive_reason or "gated")
    return f"Closed-world prior shaping is inactive ({cw.mode}: {reason_text}). "


def roster_step(
    roster: RosterHealthEnvelope | SourceFailure,
    members: list[MemberInfo] | SourceFailure | None = None,
    cts: CTSIdentityReadiness | SourceFailure | None = None,
) -> ReadinessStep:
    if isinstance(roster, SourceFailure):
        return _unknown("roster", roster)
    missing = len(roster.members_without_face_enrollment)
    clusters = roster.surfaced_unnamed_visitor_clusters
    prototypes = _prototype_counts_detail(members)
    closed_world = _closed_world_detail(cts)
    if roster.active_member_count == 0:
        return ReadinessStep(
            key="roster",
            state="blocked",
            detail=(
                "Nobody is listed. List and enroll every person who lives in the house. "
                + closed_world
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
                + closed_world
                + _ROSTER_SCOPE
            ),
            next_action="enroll_members",
        )
    if clusters:
        return ReadinessStep(
            key="roster",
            state="attention",
            detail=f"{_clusters(clusters)} {prototypes}{closed_world}{_ROSTER_SCOPE}",
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
        detail=f"{everyone} enrolled. {prototypes}{closed_world}{_ROSTER_SCOPE}",
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
    cts: CTSIdentityReadiness | SourceFailure | None = None,
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
    if health.status == ARTIFACT_INCOMPATIBLE:
        recognizer_note = (
            f" for active recognizer {health.recognizer_version}"
            if health.recognizer_version
            else ""
        )
        return ReadinessStep(
            key="artifact",
            state="blocked",
            detail=(
                "The deployed calibration artifact is incompatible with the current face "
                f"recognizer or gallery representation{recognizer_note}; refit and redeploy it."
            ),
            next_action="refit_artifact",
        )
    if health.status != ARTIFACT_READY:
        return ReadinessStep(
            key="artifact",
            state="blocked",
            detail=f"The calibration artifact is not usable (status {health.status}).",
            next_action="fit_and_deploy_artifact",
        )
    if (
        isinstance(cts, CTSIdentityReadiness)
        and cts.expected_recognizer_version
        and health.recognizer_version
        and cts.expected_recognizer_version != health.recognizer_version
    ):
        return ReadinessStep(
            key="artifact",
            state="blocked",
            detail=(
                f"Tracking expects recognizer {cts.expected_recognizer_version} while person "
                f"identification runs {health.recognizer_version}; calibrated face confidence is "
                "paused until both match and the artifact is refitted."
            ),
            next_action="refit_artifact",
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
    taught = cts.wearable_gallery_counts
    if taught is not None and (
        taught.pending_review + taught.auto_verified + taught.operator_verified + taught.rejected
    ):
        summary += (
            f" Of these, a wearable taught {taught.auto_verified + taught.operator_verified} "
            f"voting and {taught.pending_review} waiting for review."
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


def _wearables_telemetry_detail(wearables: WearablesHealth) -> str:
    parts: list[str] = []
    if wearables.nodes_heard_recent_count is not None:
        parts.append(
            f"{wearables.nodes_heard_recent_count} of {wearables.active_node_count} "
            "RF nodes heard in the last 5 minutes"
        )
    elif wearables.rf_ingress_unreachable:
        parts.append("rf-ingress health unavailable")
    if wearables.tags_heard_count is not None:
        parts.append(
            f"{wearables.tags_heard_count} of {wearables.active_device_count} "
            f"{'tag' if wearables.active_device_count == 1 else 'tags'} heard"
        )
    if wearables.lowest_battery_fraction is not None:
        parts.append(f"lowest beacon battery {round(wearables.lowest_battery_fraction * 100)}%")
    if wearables.last_heard_age_s is not None:
        parts.append(f"last fix heard {wearables.last_heard_age_s:.0f} s ago")
    elif not parts:
        return " No RF fixes heard yet."
    return " " + "; ".join(parts) + "."


def wearables_step(
    wearables: WearablesHealth | SourceFailure,
    *,
    has_floor_plan_and_scale: bool,
) -> ReadinessStep:
    """Optional wearable identity readiness step: RF nodes, consented bindings, and battery."""
    if isinstance(wearables, SourceFailure):
        return _unknown("wearables", wearables, optional=True)

    counts = (
        f"{_count(wearables.active_node_count, 'RF node')} placed, "
        f"{_count(wearables.active_device_count, 'active device')}, "
        f"{_count(wearables.active_binding_count, 'active binding')}."
    )
    if (
        wearables.active_node_count == 0
        and wearables.active_device_count == 0
        and wearables.active_binding_count == 0
    ):
        return ReadinessStep(
            key="wearables",
            state="ready",
            detail=(
                "No wearables configured yet. Wearables are optional corroborating sensors "
                "for rooms and shared spaces."
            ),
            next_action="none",
            optional=True,
        )
    if not has_floor_plan_and_scale:
        return ReadinessStep(
            key="wearables",
            state="attention",
            detail=f"{counts} Upload a floor plan and set its scale so RF nodes have floor coordinates.",
            next_action="upload_floor_plan",
            optional=True,
        )
    telemetry = _wearables_telemetry_detail(wearables)
    if wearables.low_battery_count > 0:
        return ReadinessStep(
            key="wearables",
            state="attention",
            detail=(
                f"{counts} {_count(wearables.low_battery_count, 'wearable')} reported low battery."
                + telemetry
            ),
            next_action="configure_wearables",
            optional=True,
        )
    if wearables.active_node_count == 0 or wearables.active_binding_count == 0:
        return ReadinessStep(
            key="wearables",
            state="attention",
            detail=(
                f"{counts} Place at least one RF node and bind a consented device to use wearables."
            ),
            next_action="configure_wearables",
            optional=True,
        )
    if wearables.nodes_heard_recent_count == 0 and wearables.active_node_count > 0:
        return ReadinessStep(
            key="wearables",
            state="attention",
            detail=counts + telemetry,
            next_action="configure_wearables",
            optional=True,
        )
    return ReadinessStep(
        key="wearables",
        state="ready",
        detail=counts + telemetry,
        next_action="none",
        optional=True,
    )


def wearable_learners_step(cts: CTSIdentityReadiness | SourceFailure) -> ReadinessStep:
    """Optional wearable-learners readiness step: evaluation, holds, and learner rollout."""
    if isinstance(cts, SourceFailure):
        return _unknown("wearable_learners", cts, optional=True)

    learners = cts.wearable_learners
    mode = learners.wearable_mode if learners is not None else cts.wearable_mode
    if mode == "off" or learners is None:
        return ReadinessStep(
            key="wearable_learners",
            state="blocked",
            detail=(
                "The wearable channel is off in the tracking orchestrator, so wearable learners "
                "cannot run."
            ),
            next_action="configure_wearables",
            optional=True,
        )

    if learners.open_teaching_holds > 0:
        return ReadinessStep(
            key="wearable_learners",
            state="attention",
            detail=(
                f"{_count(learners.open_teaching_holds, 'wearable tag')} "
                f"{'is' if learners.open_teaching_holds == 1 else 'are'} held from teaching "
                "after revocation or suspected swap. Review what was taught and resume teaching "
                "when the band is back on the right wearer."
            ),
            next_action="resume_wearable_teaching",
            optional=True,
        )

    taught = cts.wearable_gallery_counts
    pending_taught = taught.pending_review if taught is not None else 0
    any_learner_on = (
        learners.wearable_seeding_enabled
        or learners.face_attestation_mode == "enabled"
        or learners.wearable_backfill_enabled
    )

    if learners.evaluation_sample_rate <= 0.0:
        return ReadinessStep(
            key="wearable_learners",
            state="attention",
            detail=(
                f"Wearable mode is {mode}, but image-only evaluation sampling is off "
                "(sample_rate is 0). Enable evaluation sampling so wearable teaching can be "
                "measured."
            ),
            next_action="enable_wearable_learners",
            optional=True,
        )

    if mode == "shadow" or not any_learner_on:
        if pending_taught > 0:
            return ReadinessStep(
                key="wearable_learners",
                state="attention",
                detail=(
                    f"Wearable mode is {mode} with {_count(pending_taught, 'wearable-taught body sample')} "
                    "waiting for review."
                ),
                next_action="review_body_samples",
                optional=True,
            )
        return ReadinessStep(
            key="wearable_learners",
            state="attention",
            detail=(
                f"Wearable mode is {mode} with evaluation sampling at "
                f"{learners.evaluation_sample_rate:.0%}. Turn on wearable seeding or face "
                "attestation once shadow checks look good."
            ),
            next_action="enable_wearable_learners",
            optional=True,
        )

    days = learners.evaluation_days_14d
    diff = learners.attribution_difference_14d
    revoked_note = (
        f" {_count(learners.revoked_segments_14d, 'segment')} revoked in the last 14 days."
        if learners.revoked_segments_14d > 0
        else ""
    )
    if days == 0 or diff is None:
        return ReadinessStep(
            key="wearable_learners",
            state="attention",
            detail=(
                "Wearable learners are running, waiting for paired image-only evaluation days "
                f"over the last 14 days.{revoked_note}"
            ),
            next_action="review_shadow",
            optional=True,
        )
    if diff <= 0.0:
        return ReadinessStep(
            key="wearable_learners",
            state="attention",
            detail=(
                f"Wearable learners are running, but the 14-day image-only attribution difference "
                f"is {diff:+.3f} across {_count(days, 'day')} (not yet positive).{revoked_note}"
            ),
            next_action="review_body_samples",
            optional=True,
        )
    return ReadinessStep(
        key="wearable_learners",
        state="ready",
        detail=(
            f"Wearable learners are running with a {diff:+.3f} 14-day image-only attribution "
            f"difference across {_count(days, 'day')} and no open teaching holds.{revoked_note}"
        ),
        next_action="none",
        optional=True,
    )


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
