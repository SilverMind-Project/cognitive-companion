"""One path for every identity review decision: validate it once, let its owner apply it.

Each review surface (visitor clusters, face calibration captures, ReID body samples) registers a
``ReviewSubjectAdapter`` that knows how its owner applies a verdict: which upstream call, which
reason code, which version guard. Everything the surfaces share happens here, once, before any
adapter runs:

- the surface accepts the verdict (``vocabulary.SURFACES``);
- a verdict the surface does not allow in bulk names exactly one subject;
- a verdict that names a member gets an active household member, with enrolled faces when the
  verdict needs them, and a verdict that names nobody gets no target;
- the response carries one result per subject, the counts, and the effect sentence the browser
  previewed.

Track corrections are not a surface here: their revision ranges, optimistic proposal versions,
and projection acknowledgements are governance an adapter would have to reproduce exactly, so they
keep their own workflow. Listing subjects also stays with each surface; their list shapes differ
on purpose (clusters, captures with crops, gallery rows with eligibility).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from backend.core.exceptions import AppError, ValidationError
from backend.schemas.identity_review import (
    BatchReviewResponse,
    ReviewItemResult,
    ReviewSurface,
    ReviewVerdict,
)
from backend.services.identity_review.vocabulary import SURFACES, effect_text
from backend.services.identity_targets import IdentityTarget, IdentityTargetsService


@dataclass(frozen=True)
class ReviewSubject:
    """One thing being reviewed. ``version`` is the owner's optimistic version, where it keeps one."""

    id: str
    version: int | None = None


@dataclass(frozen=True)
class ReviewDecision:
    """A validated decision, handed to the surface's adapter."""

    surface: ReviewSurface
    verdict: ReviewVerdict
    subjects: tuple[ReviewSubject, ...]
    # The member a member verdict names, already checked; None for every other verdict.
    target: IdentityTarget | None = None
    # A surface-specific refinement of the verdict (ReID's unusable reason code).
    reason: str | None = None
    note: str | None = None


class ReviewSubjectAdapter(Protocol):
    """How one surface's owner applies a decision. Returns one result per subject, in order."""

    surface: ReviewSurface

    async def apply(self, decision: ReviewDecision, *, actor: str) -> list[ReviewItemResult]: ...


class ReviewSurfaceUnavailable(AppError):
    """No adapter is registered for the surface (its owner is not running in this deployment)."""

    def __init__(self, surface: str) -> None:
        super().__init__(f"{surface} review is not available", status_code=503)


class IdentityReviewRegistry:
    def __init__(self, targets: IdentityTargetsService) -> None:
        self._targets = targets
        self._adapters: dict[ReviewSurface, ReviewSubjectAdapter] = {}

    def register(self, adapter: ReviewSubjectAdapter) -> None:
        if adapter.surface in self._adapters:
            raise ValueError(f"{adapter.surface} already has a review adapter")
        self._adapters[adapter.surface] = adapter

    def surfaces(self) -> list[ReviewSurface]:
        return list(self._adapters)

    async def decide(
        self,
        surface: ReviewSurface,
        verdict: ReviewVerdict,
        subjects: Sequence[ReviewSubject],
        *,
        actor: str,
        target_identity_id: str | None = None,
        reason: str | None = None,
        note: str | None = None,
    ) -> BatchReviewResponse:
        """Validate a decision, apply it through the surface's adapter, and report it.

        Raises ``ValidationError`` (422) for a verdict the surface does not accept, several
        subjects for a one-at-a-time verdict, or a missing, unexpected, or ineligible target;
        ``ReviewSurfaceUnavailable`` (503) when the surface's owner is not running. Upstream
        failures propagate as the adapter's owner raises them.
        """
        adapter = self._adapters.get(surface)
        if adapter is None:
            raise ReviewSurfaceUnavailable(surface)
        try:
            spec = SURFACES[surface].verdict(verdict)
        except KeyError as exc:
            raise ValidationError(f"{surface} does not accept {verdict}") from exc
        if not subjects:
            raise ValidationError("a decision needs at least one subject")
        if len(subjects) > 1 and not spec.batch:
            raise ValidationError(f"{verdict} on {surface} is decided one subject at a time")

        target: IdentityTarget | None = None
        if spec.needs_target:
            if target_identity_id is None:
                raise ValidationError(f"{verdict} needs target_identity_id")
            target = await self._targets.require_member(
                target_identity_id, enrolled_face=spec.needs_enrolled_face
            )
        elif target_identity_id is not None:
            raise ValidationError(f"{verdict} names nobody; drop target_identity_id")

        decision = ReviewDecision(
            surface=surface,
            verdict=verdict,
            subjects=tuple(subjects),
            target=target,
            reason=reason,
            note=note,
        )
        results = await adapter.apply(decision, actor=actor)
        reviewed = sum(1 for r in results if r.ok)
        return BatchReviewResponse(
            results=results,
            reviewed=reviewed,
            failed=len(results) - reviewed,
            effect=effect_text(surface, verdict, member=target.display_name if target else None),
        )
