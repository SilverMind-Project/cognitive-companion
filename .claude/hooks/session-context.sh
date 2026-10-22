#!/usr/bin/env bash
# cognitive-companion: SessionStart context (startup and after compaction), at most 10 lines (EG-M06).
set -u
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" 2>/dev/null || exit 0
branch=$(git branch --show-current 2>/dev/null)
dirty=$(git status --short 2>/dev/null | wc -l)
echo "[cognitive-companion] branch ${branch:-?}, ${dirty// /} files changed or untracked."
echo "Gates: make check (fast: lint, mypy core, core tests); make check-all (full: every backend test plus frontend)."
echo "Format only the files you touched; never ruff format the whole backend."
echo "backend/uv.lock must not change unless you re-lock on purpose (UV_FROZEN=1 is set)."
echo "Guards: .claude/hooks/ (project) and ~/.claude/hooks/guard-machine.sh (machine). Override with ! if intended."
