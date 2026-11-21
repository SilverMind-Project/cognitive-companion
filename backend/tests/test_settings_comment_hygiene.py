"""Guard that settings.yaml comments state rationale directly, without program or decision ids."""

from __future__ import annotations

import re
from pathlib import Path

_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"

_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("milestone id", re.compile(r"\b(?:(?:IR|DL|EG)-)?[MS]\d{2}\b")),
    ("short milestone id", re.compile(r"\(M\d(?:\.\d)?\b")),
    ("decision id", re.compile(r"\bdecision\s+[A-Z]\d+\b", re.IGNORECASE)),
    ("parenthetical decision/finding id", re.compile(r"\([DFRVGL]\d+\)")),
    ("program milestone reference", re.compile(r"\bMilestone\s+\d+\b", re.IGNORECASE)),
)


def _comment_lines(path: Path) -> list[tuple[int, str]]:
    comments: list[tuple[int, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("#"):
            comments.append((lineno, stripped))
        elif " #" in raw:
            comments.append((lineno, raw.split(" #", 1)[1]))
    return comments


def test_settings_comments_have_no_milestone_or_decision_ids() -> None:
    comments = _comment_lines(_SETTINGS_PATH)
    # Non-vacuity canary: settings.yaml must carry explanatory comments.
    assert len(comments) >= 30
    violations: list[str] = []
    for lineno, text in comments:
        for label, pattern in _FORBIDDEN_PATTERNS:
            if match := pattern.search(text):
                violations.append(
                    f"{_SETTINGS_PATH.name}:{lineno}: {label} {match.group(0)!r} in {text!r}"
                )
    assert not violations, "Settings comments must state rationale directly:\n" + "\n".join(
        violations
    )
