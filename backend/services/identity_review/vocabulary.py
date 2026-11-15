"""What each identity decision does, per review surface, stated once.

Every surface where an operator says who a face, body, or track belongs to speaks the shared
verdicts of ``backend/schemas/identity_review.py``. What a verdict *does* differs by owner: marking
a visitor cluster closes it, labeling a calibration face feeds the calibration fit, approving a
body sample gives it a vote in body recognition. The sentence that says so is defined here, once,
and is both the preview the browser shows before a decision and the ``effect`` a batch response
reports after it. The browser never writes its own copy.

An effect may name the chosen member with the ``{member}`` placeholder; ``effect_text`` fills it.

Each surface also states its ``guarantee``: which of its decisions can change face enrollment.
Only naming a new person does, anywhere; review never quietly widens what the system recognizes as
someone already enrolled.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.schemas.identity_review import (
    ReviewSurface,
    ReviewSurfaceOut,
    ReviewVerdict,
    ReviewVerdictOut,
    ReviewVocabularyEnvelope,
)

MEMBER_PLACEHOLDER = "{member}"


@dataclass(frozen=True)
class VerdictSpec:
    verdict: ReviewVerdict
    effect: str
    # The verdict names a household member (``target_identity_id``).
    needs_target: bool = False
    # The named member must have enrolled faces in person identification.
    needs_enrolled_face: bool = False
    # The surface accepts this verdict for several subjects in one decision.
    batch: bool = False


@dataclass(frozen=True)
class SurfaceSpec:
    surface: ReviewSurface
    guarantee: str
    verdicts: tuple[VerdictSpec, ...]

    def verdict(self, verdict: ReviewVerdict) -> VerdictSpec:
        for spec in self.verdicts:
            if spec.verdict == verdict:
                return spec
        raise KeyError(f"{self.surface} does not accept {verdict}")


_VISITOR_CLOSED = (
    "The groups stop appearing for review and nothing is enrolled. Look-alike faces join these "
    "groups quietly instead of starting new ones."
)

SURFACES: dict[ReviewSurface, SurfaceSpec] = {
    "visitors": SurfaceSpec(
        surface="visitors",
        guarantee="Only naming someone new changes face enrollment.",
        verdicts=(
            VerdictSpec(
                verdict="is_member",
                effect=(
                    "The groups are marked as {member}'s faces and stop appearing for review. "
                    "Nothing is added to {member}'s enrollment, so recognition does not change. "
                    "Look-alike faces join these groups quietly."
                ),
                needs_target=True,
                needs_enrolled_face=True,
                batch=True,
            ),
            VerdictSpec(
                verdict="new_person",
                effect=(
                    "A new person is added to the household and these faces are enrolled as "
                    "theirs, so the cameras start recognizing them."
                ),
            ),
            VerdictSpec(verdict="not_enrolled", effect=_VISITOR_CLOSED, batch=True),
            VerdictSpec(verdict="not_usable", effect=_VISITOR_CLOSED, batch=True),
        ),
    ),
    "face_calibration": SurfaceSpec(
        surface="face_calibration",
        guarantee="Labels feed only the calibration fit; face enrollment never changes.",
        verdicts=(
            VerdictSpec(
                verdict="is_member",
                effect=(
                    "The face is labeled as {member} and counts toward the calibration fit as a "
                    "true match. {member}'s enrollment does not change."
                ),
                needs_target=True,
                needs_enrolled_face=True,
            ),
            VerdictSpec(
                verdict="not_enrolled",
                effect=(
                    "The face is labeled as someone outside the household, which teaches the "
                    "calibration fit what a non-match looks like. Nothing is enrolled."
                ),
            ),
            VerdictSpec(
                verdict="not_usable",
                effect="The face is left out of the calibration fit. Nothing is enrolled.",
            ),
        ),
    ),
    "reid_review": SurfaceSpec(
        surface="reid_review",
        guarantee=(
            "A verified body sample votes in body recognition only; face enrollment never changes."
        ),
        verdicts=(
            VerdictSpec(
                verdict="is_member",
                effect=(
                    "The body sample is verified as {member} and starts voting for them in body "
                    "recognition. Face enrollment does not change."
                ),
                needs_target=True,
            ),
            VerdictSpec(
                verdict="not_enrolled",
                effect=(
                    "The body sample is rejected as the wrong person: its crop is deleted and it "
                    "never votes in body recognition."
                ),
                batch=True,
            ),
            VerdictSpec(
                verdict="not_usable",
                effect=(
                    "The body sample is rejected as unusable: its crop is deleted and it never "
                    "votes in body recognition."
                ),
                batch=True,
            ),
        ),
    ),
}


def effect_text(surface: ReviewSurface, verdict: ReviewVerdict, member: str | None = None) -> str:
    """The effect sentence for ``verdict`` on ``surface``, with the member's name filled in."""
    text = SURFACES[surface].verdict(verdict).effect
    if MEMBER_PLACEHOLDER in text:
        if member is None:
            raise ValueError(f"{surface}/{verdict} effect names a member; pass member=")
        text = text.replace(MEMBER_PLACEHOLDER, member)
    return text


def vocabulary_envelope() -> ReviewVocabularyEnvelope:
    """Every surface's verdicts and effects, for the browser to preview before a decision."""
    return ReviewVocabularyEnvelope(
        surfaces=[
            ReviewSurfaceOut(
                surface=spec.surface,
                guarantee=spec.guarantee,
                verdicts=[
                    ReviewVerdictOut(
                        verdict=v.verdict,
                        effect=v.effect,
                        needs_target=v.needs_target,
                        needs_enrolled_face=v.needs_enrolled_face,
                        batch=v.batch,
                    )
                    for v in spec.verdicts
                ],
            )
            for spec in SURFACES.values()
        ],
        member_placeholder=MEMBER_PLACEHOLDER,
    )
