"""The identity readiness service reads every source once and degrades per source."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from backend.core.upstream_errors import UpstreamUnavailable
from backend.integrations.person_id_client import (
    CalibrationHealthInfo,
    CalibrationSummaryInfo,
    MemberInfo,
    PersonIDUpstreamError,
)
from backend.models.cts_camera import CtsCamera
from backend.models.room import Room
from backend.schemas.identity_roster import RosterHealthEnvelope, RosterMemberRef
from backend.services.identity_readiness import IdentityReadinessService

_AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


class _Roster:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def get_roster_health(self) -> RosterHealthEnvelope:
        if self._error is not None:
            raise self._error
        return RosterHealthEnvelope(
            members_without_face_enrollment=[
                RosterMemberRef(member_id="m2", name="M2", embedding_count=3)
            ],
            active_member_count=2,
            min_face_embeddings=5,
            visitor_clustering_enabled=True,
            surfaced_unnamed_visitor_clusters=1,
            is_complete=False,
            checked_at=_AT,
        )


class _PersonID:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def _check(self) -> None:
        if self._error is not None:
            raise self._error

    async def get_calibration_summary(self) -> CalibrationSummaryInfo:
        self._check()
        return CalibrationSummaryInfo(
            by_state={"unlabeled": 0, "labeled": 0, "rejected": 0},
            by_label_kind={},
            by_quality_decile={},
            by_camera={},
            identities=[],
            not_enrolled_episodes=0,
            capture_enabled=False,
        )

    async def get_calibration_health(self) -> CalibrationHealthInfo:
        self._check()
        return CalibrationHealthInfo(
            status="degraded_missing", covered_identities=None, template_status="degraded_missing"
        )

    async def list_members(self) -> list[MemberInfo]:
        self._check()
        return [MemberInfo(person_id="m1", name="M1", embedding_count=7, created_at=_AT)]


class _Orchestrator:
    def __init__(self, body: dict[str, Any] | Exception) -> None:
        self._body = body

    async def identity_readiness(self) -> dict[str, Any]:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _Ingress:
    def __init__(self, ages: dict[str, float | None]) -> None:
        self._ages = ages
        self.calls: list[str] = []

    async def stream_health(self, *, camera_id: str) -> dict[str, Any]:
        self.calls.append(camera_id)
        age = self._ages[camera_id]
        if age is None:
            raise UpstreamUnavailable("rtsp_ingress", 503)
        return {"camera_id": camera_id, "last_frame_age_s": age}


_CTS_BODY: dict[str, Any] = {
    "face_evidence_policy": "shadow",
    "face_templates_mode": "off",
    "face_quality_mode": "shadow",
    "cc_assertion_mode": "shadow",
    "expected_arcface_model_version": None,
    "expected_quality_version": "heuristic-v1",
    "reid_gallery_counts": {
        "pending_review": 0,
        "auto_verified": 0,
        "operator_verified": 0,
        "rejected": 0,
    },
    "cameras": [{"camera_id": "hall", "calibrated": False}],
    "overlap_group_count": 0,
    "identities_known": 2,
}


@pytest.fixture
def household(db_factory):
    db = db_factory()
    db.add_all(
        [
            Room(name="Hall"),
            Room(name="Kitchen"),
            CtsCamera(id="hall", name="Hall", role="mixed", enabled=True),
            CtsCamera(id="kitchen", name="Kitchen", role="surveillance", enabled=True),
            CtsCamera(id="old", name="Old", role="mixed", enabled=False),
        ]
    )
    db.commit()
    db.close()


def _service(
    db_factory,
    *,
    roster: _Roster | None = None,
    person_id: _PersonID | None = None,
    orchestrator: _Orchestrator | None = None,
    ingress: _Ingress | None = None,
) -> IdentityReadinessService:
    return IdentityReadinessService(
        roster=roster or _Roster(),  # type: ignore[arg-type]
        person_id=person_id or _PersonID(),  # type: ignore[arg-type]
        session_factory=db_factory,
        orchestrator=orchestrator,  # type: ignore[arg-type]
        ingress=ingress,  # type: ignore[arg-type]
        clock=lambda: _AT,
    )


def _states(envelope) -> dict[str, str]:
    return {s.key: s.state for s in envelope.steps}


async def test_todays_household_is_blocked_at_the_floor_frame(db_factory, household) -> None:
    ingress = _Ingress({"hall": 0.4, "kitchen": 0.9})
    envelope = await _service(
        db_factory, orchestrator=_Orchestrator(_CTS_BODY), ingress=ingress
    ).get_readiness()

    assert [s.key for s in envelope.steps] == [
        "roster",
        "ingest",
        "floor_frame",
        "capture",
        "labeling",
        "artifact",
        "face_policy",
        "templates",
        "body_gallery",
    ]
    assert envelope.blocking_step == "floor_frame"
    assert _states(envelope) == {
        "roster": "attention",
        "ingest": "ready",
        "floor_frame": "blocked",
        "capture": "blocked",
        "labeling": "blocked",
        "artifact": "blocked",
        "face_policy": "attention",
        "templates": "blocked",
        "body_gallery": "blocked",
    }
    assert [(q.surface, q.waiting) for q in envelope.review_queues] == [
        ("visitors", 1),
        ("face_calibration", 0),
        ("reid_review", 0),
    ]
    # Only enabled cameras are probed.
    assert sorted(ingress.calls) == ["hall", "kitchen"]
    assert envelope.checked_at == _AT


async def test_stopped_person_id_is_unknown_for_its_steps_only(db_factory, household) -> None:
    down = PersonIDUpstreamError(502, "Person identification service is unreachable")
    envelope = await _service(
        db_factory,
        roster=_Roster(error=down),
        person_id=_PersonID(error=down),
        orchestrator=_Orchestrator(_CTS_BODY),
        ingress=_Ingress({"hall": 0.4, "kitchen": 0.9}),
    ).get_readiness()

    states = _states(envelope)
    for key in ("roster", "capture", "labeling", "artifact", "templates"):
        assert states[key] == "unknown", key
    # A queue whose owner could not be read has no count, never a zero.
    assert {q.surface: q.waiting for q in envelope.review_queues} == {
        "visitors": None,
        "face_calibration": None,
        "reid_review": 0,
    }
    assert states["ingest"] == "ready"
    assert states["face_policy"] == "attention"
    assert states["floor_frame"] == "blocked"


async def test_stopped_cts_is_unknown_for_its_steps_only(db_factory, household) -> None:
    envelope = await _service(
        db_factory,
        orchestrator=_Orchestrator(UpstreamUnavailable("tracking_orchestrator", 503)),
        ingress=_Ingress({"hall": None, "kitchen": 0.9}),
    ).get_readiness()

    states = _states(envelope)
    for key in ("face_policy", "templates", "body_gallery", "ingest"):
        assert states[key] == "unknown", key
    assert {q.surface: q.waiting for q in envelope.review_queues}["reid_review"] is None
    assert states["roster"] == "attention"
    assert states["capture"] == "blocked"


async def test_cts_contract_violation_is_unknown_not_a_crash(db_factory, household) -> None:
    envelope = await _service(
        db_factory,
        orchestrator=_Orchestrator({"face_evidence_policy": "shadow"}),
        ingress=_Ingress({"hall": 0.4, "kitchen": 0.9}),
    ).get_readiness()

    assert _states(envelope)["face_policy"] == "unknown"


async def test_cts_disabled_reports_unknown_cts_steps(db_factory, household) -> None:
    envelope = await _service(db_factory).get_readiness()

    states = _states(envelope)
    assert states["ingest"] == "unknown"
    assert states["face_policy"] == "unknown"
    assert "CTS is disabled" in next(s.detail for s in envelope.steps if s.key == "ingest")
