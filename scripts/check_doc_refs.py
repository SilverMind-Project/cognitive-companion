#!/usr/bin/env python3
"""Fail when an instruction file names a repository file that does not exist (EG-M08/M09/M10).

Scans CLAUDE.md, AGENTS.md, .claude/skills/**/*.md, and .claude/rules/**/*.md for backticked
file references and absolute workspace paths, and reports any that resolve nowhere. A skill
that points an agent at a renamed or deleted file is how stale guidance spreads.

    python scripts/check_doc_refs.py            check this repository
    python scripts/check_doc_refs.py --root DIR check another tree (used by the test)

A reference resolves when it exists relative to one of RESOLVE_ROOTS, or (for a bare file name)
when any tracked file has that name. References into a sibling repository resolve against the
workspace when it is checked out next to this one, and are skipped otherwise (CI clones one
repository). Placeholders such as NNNN_*, my_*, Foo*, and <name> are ignored.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Directories, relative to the repository root, that a relative reference may be written against.
RESOLVE_ROOTS: tuple[str, ...] = ("", "backend", "frontend", "frontend/src")

# Sibling repositories a reference may name with a leading "<repo>/" prefix.
SIBLINGS: tuple[str, ...] = (
    "cognitive-companion",
    "continuous-tracking",
    "person-identification-service",
    "silvermind-project.github.io",
    "scene-analysis-service",
    "semantic-memory-service",
    "tts-service",
    "cts-contracts",
    "triton-shared",
)
WORKSPACE_PREFIX = "/home/sriram/code/nanai/"

EXTENSIONS = (
    ".py",
    ".md",
    ".ts",
    ".js",
    ".mjs",
    ".vue",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".css",
    ".json",
    ".sh",
    ".go",
    ".proto",
    ".pbtxt",
    ".txt",
    ".ini",
    ".cfg",
)
BACKTICK = re.compile(r"`([^`\n]+)`")
ABSOLUTE = re.compile(r"(/home/sriram/code/nanai/[A-Za-z0-9_./-]+)")
PLACEHOLDER = re.compile(
    r"NNNN|\bmy_|my-resource|Foo|NewResource|PascalCase|camelCase|snake_case|<[^>]*>|[*{}$]|"
    r"\.\.\.|_hooktest|\bxxx\b|example",
)

# Names that are mentioned on purpose although no such file exists (a library, or a file the
# text says was deleted and must not come back). Keep this short; each entry needs its reason.
ALLOWED_MISSING: dict[str, str] = {
    "chart.js": "a charting library the data-visualization skill forbids, not a file",
    "contracts.js": "the deleted frontend contract checker; the skill says never reintroduce it",
    "r4_bypass_guard.spec.js": "a deleted spec, converted to ESLint rules",
}

# A reference written relative to a sibling package rather than this repository.
ALIASES: dict[str, str] = {
    "@/": "frontend/src/",
    "cts_contracts/": "../cts-contracts/cts_contracts/",
}

INSTRUCTION_GLOBS = (
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/skills/**/*.md",
    ".claude/rules/**/*.md",
)


def tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
        ).stdout
        return out.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]


def candidate(token: str) -> str | None:
    """Return the path part of a backticked token if it looks like a file reference."""
    token = token.strip().split("::", 1)[0].rstrip(".,;:)")
    token = re.sub(r":\d+(-\d+)?$", "", token)  # file.py:123
    if " " in token or PLACEHOLDER.search(token):
        return None
    if token.startswith(("http://", "https://")):
        return None
    token = token.removeprefix("./")
    for alias, target in ALIASES.items():
        if token.startswith(alias):
            token = target + token[len(alias) :]
    if token.startswith(".") and "/" not in token:
        return None  # a bare extension such as `.py` or `.up.sql`
    if Path(token).name in ALLOWED_MISSING:
        return None
    if token.startswith("/") and not token.startswith(WORKSPACE_PREFIX):
        return None  # an API route such as /api/v1/rooms
    if not token.endswith(EXTENSIONS):
        return None
    return token


def resolves(token: str, root: Path, names: set[str]) -> bool | None:
    """True if found, False if missing, None if it cannot be checked here."""
    if token.startswith(WORKSPACE_PREFIX):
        return Path(token).exists() if Path(WORKSPACE_PREFIX).is_dir() else None
    first = token.split("/", 1)[0]
    if first in SIBLINGS and first != root.name:
        sibling = root.parent / first
        return (root.parent / token).exists() if sibling.is_dir() else None
    if token.startswith("../"):
        target = (root / token).resolve()
        return target.exists() if target.parent.parent.is_dir() else None
    for base in RESOLVE_ROOTS:
        if (root / base / token).exists():
            return True
    if "/" not in token:
        return token in names
    # A path written relative to some nested package directory: accept a unique suffix match.
    return any(f.endswith("/" + token) for f in names_full(root))


_NAMES_FULL: list[str] = []


def names_full(root: Path) -> list[str]:
    global _NAMES_FULL
    if not _NAMES_FULL:
        _NAMES_FULL = tracked_files(root)
    return _NAMES_FULL


def instruction_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in INSTRUCTION_GLOBS:
        files.extend(sorted(root.glob(pattern)))
    return [f for f in files if f.is_file()]


def check(root: Path) -> list[str]:
    names = {Path(f).name for f in names_full(root)}
    problems: list[str] = []
    for doc in instruction_files(root):
        in_fence = False
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue  # code blocks show commands and examples, not references
            tokens = [m.group(1) for m in BACKTICK.finditer(line)]
            tokens += ABSOLUTE.findall(line)
            for raw in tokens:
                token = candidate(raw)
                if token is None:
                    continue
                if resolves(token, root, names) is False:
                    problems.append(f"{doc.relative_to(root)}:{lineno}: {token}")
    return sorted(set(problems))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    problems = check(args.root.resolve())
    for p in problems:
        sys.stdout.write(f"{p}: no such file\n")
    if problems:
        sys.stderr.write(
            f"{len(problems)} dead file reference(s) in instruction files\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
