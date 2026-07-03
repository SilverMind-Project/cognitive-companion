"""Assert CLAUDE.md and AGENTS.md list exactly the registered steps/channels/filters.

Guards against the drift found in the July 2026 review: CLAUDE.md, AGENTS.md,
and docs/systems-architecture.md each listed a different step count (23, 22,
24) and none matched the 24 actually registered. Run this whenever a step,
channel, or filter is added, removed, or renamed and update the two markdown
files in the same change.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.channels import ChannelRegistry
from backend.filters import FilterRegistry
from backend.steps import StepRegistry

ChannelRegistry.discover()
FilterRegistry.discover()
StepRegistry.discover()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_AGENTS_MD = _REPO_ROOT / "AGENTS.md"


def _backtick_tokens(text: str) -> set[str]:
    return set(re.findall(r"`([a-z_]+)`", text))


def _assert_same_names(registered: set[str], documented: set[str], where: str) -> None:
    missing_from_doc = registered - documented
    extra_in_doc = documented - registered
    message = (
        f"{where} out of sync with the registry.\n"
        f"  Registered but not documented: {sorted(missing_from_doc) or 'none'}\n"
        f"  Documented but not registered: {sorted(extra_in_doc) or 'none'}"
    )
    assert not missing_from_doc, message
    assert not extra_in_doc, message


def _claude_md_list(text: str, prefix: str) -> str:
    """Return just the backtick list on the `{prefix} \\`a\\`, \\`b\\`....` line.

    Stops at the first ". " after the prefix so trailing prose on the same
    line (e.g. CLAUDE.md's step-types line explains `media_window_poll` and
    names the two *removed* step types in the following sentences) is not
    swept into the token set.
    """
    match = re.search(rf"^{re.escape(prefix)} (.*?)\.\s", text, re.MULTILINE)
    if not match:
        raise AssertionError(f"No line starting with {prefix!r} found in CLAUDE.md")
    return match.group(1)


def _agents_md_section(text: str, heading: str) -> str:
    """Return the AGENTS.md subsection body between `heading` and the next `### `."""
    pattern = re.compile(rf"^{re.escape(heading)}\n(.*?)(?=^### |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"No {heading!r} section found in AGENTS.md")
    return match.group(1)


def _agents_md_count(section: str, noun: str) -> int:
    match = re.search(rf"There are (\d+) (?:registered )?{noun}", section)
    if not match:
        raise AssertionError(f"No 'There are N {noun}' line found")
    return int(match.group(1))


def _agents_md_list_paragraph(section: str) -> str:
    """Return the first paragraph in `section` that opens with a backtick.

    The step-types section has a second, unrelated paragraph explaining
    `media_window_poll` and naming the two removed step types; only the
    first paragraph is the actual registered-name list.
    """
    for paragraph in section.split("\n\n"):
        stripped = paragraph.strip()
        if stripped.startswith("`"):
            return stripped
    raise AssertionError("No backtick-list paragraph found in section")


class TestClaudeMdParity:
    """CLAUDE.md's single-line `Current built-in step types: ...` and friends."""

    def test_step_types(self) -> None:
        text = _CLAUDE_MD.read_text()
        list_text = _claude_md_list(text, "Current built-in step types:")
        _assert_same_names(
            set(StepRegistry.all_names()), _backtick_tokens(list_text), "CLAUDE.md step types"
        )

    def test_channels(self) -> None:
        text = _CLAUDE_MD.read_text()
        list_text = _claude_md_list(text, "Channels:")
        _assert_same_names(
            set(ChannelRegistry.all_names()), _backtick_tokens(list_text), "CLAUDE.md channels"
        )

    def test_filters(self) -> None:
        text = _CLAUDE_MD.read_text()
        list_text = _claude_md_list(text, "Filters:")
        _assert_same_names(
            set(FilterRegistry.all_names()), _backtick_tokens(list_text), "CLAUDE.md filters"
        )


class TestAgentsMdParity:
    """AGENTS.md's `### Step types` / `### Channels` / `### Filters` sections."""

    def test_step_types(self) -> None:
        text = _AGENTS_MD.read_text()
        section = _agents_md_section(text, "### Step types")
        registered = set(StepRegistry.all_names())
        list_text = _agents_md_list_paragraph(section)
        _assert_same_names(registered, _backtick_tokens(list_text), "AGENTS.md step types")
        count = _agents_md_count(section, "built-in step types")
        assert count == len(registered), (
            f"AGENTS.md says {count} registered step types but {len(registered)} are registered"
        )

    def test_channels(self) -> None:
        text = _AGENTS_MD.read_text()
        section = _agents_md_section(text, "### Channels")
        registered = set(ChannelRegistry.all_names())
        list_text = _agents_md_list_paragraph(section)
        _assert_same_names(registered, _backtick_tokens(list_text), "AGENTS.md channels")
        count = _agents_md_count(section, "channel types")
        assert count == len(registered), (
            f"AGENTS.md says {count} channel types but {len(registered)} are registered"
        )

    def test_filters(self) -> None:
        text = _AGENTS_MD.read_text()
        section = _agents_md_section(text, "### Filters")
        registered = set(FilterRegistry.all_names())
        list_text = _agents_md_list_paragraph(section)
        _assert_same_names(registered, _backtick_tokens(list_text), "AGENTS.md filters")
        count = _agents_md_count(section, "filter types")
        assert count == len(registered), (
            f"AGENTS.md says {count} filter types but {len(registered)} are registered"
        )
