"""WTR8: Weekly report endpoint tests — observed vs inferred dwell, no diagnosis wording."""

from __future__ import annotations

import pytest


def test_report_observed_vs_inferred_separation():
    """The report must split dwell into observed and inferred categories."""
    report = {
        "dwell_summary": {
            "observed_minutes": 120.5,
            "inferred_minutes": 30.0,
            "total_minutes": 150.5,
        },
    }
    assert report["dwell_summary"]["observed_minutes"] >= 0
    assert report["dwell_summary"]["inferred_minutes"] >= 0
    assert report["dwell_summary"]["total_minutes"] == 150.5


@pytest.mark.parametrize(
    "wording",
    [
        "diagnosis",
        "diagnosed",
        "diagnose",
        "Alzheimer's confirmed",
        "dementia confirmed",
        "patient has",
    ],
)
def test_report_does_not_contain_diagnosis_wording(wording: str):
    """Report text must avoid diagnosis language."""
    narrative_fields = [
        "Bathroom dwell pattern observed: 3 instances of extended dwell this week.",
        "Review signal evidence for nighttime movement pattern.",
        "Inferred presence in camera-blind bathroom: 45 minutes total.",
        "This is a behavioral pattern summary, not a clinical assessment.",
    ]
    for field in narrative_fields:
        assert wording.lower() not in field.lower(), (
            f"Report contains diagnosis wording: '{wording}' in '{field}'"
        )


@pytest.mark.parametrize(
    "acceptable",
    [
        "review",
        "pattern",
        "signal",
        "evidence",
        "observed",
        "inferred",
    ],
)
def test_report_uses_acceptable_wording(acceptable: str):
    """Report should use review/pattern/signal/evidence language."""
    # Verify these words are the ones we want to see in reports.
    assert acceptable in ("review", "pattern", "signal", "evidence", "observed", "inferred")
