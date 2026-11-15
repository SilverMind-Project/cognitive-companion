"""The identity review registry validates every decision once, then lets its owner apply it."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.core.exceptions import ValidationError
from backend.schemas.identity_review import ReviewItemResult
from backend.services.identity_review.registry import (
    IdentityReviewRegistry,
    ReviewDecision,
    ReviewSubject,
    ReviewSurfaceUnavailable,
)
from backend.services.identity_review.vocabulary import effect_text
from backend.services.identity_targets import IdentityTarget

_AMMA = IdentityTarget(identity_id="amma", display_name="Amma", is_active=True, is_guest=False)


class _Adapter:
    def __init__(self, surface: str) -> None:
        self.surface = surface
        self.decisions: list[ReviewDecision] = []

    async def apply(self, decision: ReviewDecision, *, actor: str) -> list[ReviewItemResult]:
        self.decisions.append(decision)
        return [ReviewItemResult(id=s.id, ok=s.id != "gone") for s in decision.subjects]


def _registry(*surfaces: str) -> tuple[IdentityReviewRegistry, dict[str, _Adapter], AsyncMock]:
    targets = AsyncMock()
    targets.require_member.return_value = _AMMA
    registry = IdentityReviewRegistry(targets)
    adapters = {s: _Adapter(s) for s in surfaces}
    for adapter in adapters.values():
        registry.register(adapter)  # type: ignore[arg-type]
    return registry, adapters, targets


async def test_a_batch_decision_reports_each_subject_counts_and_the_effect() -> None:
    registry, adapters, _ = _registry("reid_review")

    result = await registry.decide(
        "reid_review",
        "not_usable",
        [ReviewSubject("c1", 3), ReviewSubject("gone", 1)],
        actor="a",
        reason="low_quality",
    )

    assert [(r.id, r.ok) for r in result.results] == [("c1", True), ("gone", False)]
    assert (result.reviewed, result.failed) == (1, 1)
    assert result.effect == effect_text("reid_review", "not_usable")
    decision = adapters["reid_review"].decisions[0]
    assert (decision.reason, decision.subjects[0].version) == ("low_quality", 3)


async def test_a_member_verdict_gets_a_checked_member_and_names_them() -> None:
    registry, adapters, targets = _registry("face_calibration")

    result = await registry.decide(
        "face_calibration", "is_member", [ReviewSubject("k1")], actor="a", target_identity_id="amma"
    )

    targets.require_member.assert_awaited_once_with("amma", enrolled_face=True)
    assert adapters["face_calibration"].decisions[0].target == _AMMA
    assert "Amma" in result.effect


@pytest.mark.parametrize(
    ("surface", "verdict", "subjects", "target", "message"),
    [
        ("face_calibration", "new_person", ["k1"], None, "does not accept"),
        ("face_calibration", "is_member", ["k1", "k2"], "amma", "one subject at a time"),
        ("reid_review", "is_member", ["c1", "c2"], "amma", "one subject at a time"),
        ("visitors", "is_member", ["c1"], None, "needs target_identity_id"),
        ("visitors", "not_usable", ["c1"], "amma", "names nobody"),
        ("visitors", "not_usable", [], None, "at least one subject"),
    ],
)
async def test_invalid_decisions_never_reach_the_owner(
    surface: str, verdict: str, subjects: list[str], target: str | None, message: str
) -> None:
    registry, adapters, _ = _registry("visitors", "face_calibration", "reid_review")

    with pytest.raises(ValidationError, match=message):
        await registry.decide(
            surface,  # type: ignore[arg-type]
            verdict,  # type: ignore[arg-type]
            [ReviewSubject(s) for s in subjects],
            actor="a",
            target_identity_id=target,
        )
    assert all(not a.decisions for a in adapters.values())


async def test_an_ineligible_member_never_reaches_the_owner() -> None:
    registry, adapters, targets = _registry("visitors")
    targets.require_member.side_effect = ValidationError("guest has no enrolled face photos")

    with pytest.raises(ValidationError):
        await registry.decide(
            "visitors", "is_member", [ReviewSubject("c1")], actor="a", target_identity_id="guest"
        )
    assert not adapters["visitors"].decisions


async def test_an_unregistered_surface_is_unavailable() -> None:
    registry, _, _ = _registry("visitors")

    with pytest.raises(ReviewSurfaceUnavailable) as exc_info:
        await registry.decide("reid_review", "not_usable", [ReviewSubject("c1")], actor="a")
    assert exc_info.value.status_code == 503


def test_a_surface_registers_once() -> None:
    registry, _, _ = _registry("visitors")

    with pytest.raises(ValueError, match="already has"):
        registry.register(_Adapter("visitors"))  # type: ignore[arg-type]
    assert registry.surfaces() == ["visitors"]
