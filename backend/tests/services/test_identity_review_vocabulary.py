"""The review vocabulary states, once, what every identity decision changes."""

from __future__ import annotations

import pytest

from backend.services.identity_review.vocabulary import (
    MEMBER_PLACEHOLDER,
    SURFACES,
    effect_text,
    vocabulary_envelope,
)


def test_every_member_verdict_names_the_member_and_no_other_does() -> None:
    for spec in SURFACES.values():
        for verdict in spec.verdicts:
            assert (MEMBER_PLACEHOLDER in verdict.effect) == verdict.needs_target, (
                spec.surface,
                verdict.verdict,
            )


def test_only_naming_someone_new_changes_enrollment() -> None:
    # The guard against quiet overfitting: no review decision except naming a new person may
    # say it enrolls anything.
    for spec in SURFACES.values():
        for verdict in spec.verdicts:
            enrolls = "enrolled as" in verdict.effect
            assert enrolls == (verdict.verdict == "new_person"), (spec.surface, verdict.verdict)


def test_effect_text_fills_the_member() -> None:
    text = effect_text("reid_review", "is_member", member="Resident")

    assert MEMBER_PLACEHOLDER not in text
    assert text.startswith("The body sample is verified as Resident")


def test_effect_text_refuses_a_member_verdict_without_a_member() -> None:
    with pytest.raises(ValueError, match="names a member"):
        effect_text("visitors", "is_member")


def test_a_surface_rejects_a_verdict_it_does_not_accept() -> None:
    with pytest.raises(KeyError):
        effect_text("face_calibration", "new_person")


def test_envelope_lists_every_surface_in_order() -> None:
    envelope = vocabulary_envelope()

    assert [s.surface for s in envelope.surfaces] == ["visitors", "face_calibration", "reid_review"]
    assert envelope.member_placeholder == MEMBER_PLACEHOLDER
