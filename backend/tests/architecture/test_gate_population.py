"""The backend test gates must run the whole backend test tree.

``make check-all`` and ``make coverage-gate`` (the CI backend job) once passed only
``backend/tests/core`` and ``backend/tests/services`` to pytest, so the router, MCP, step,
filter, and integration suites ran in no gate. This test reads what the gate *commands* pass
to pytest (``make -n`` prints them without executing anything), so narrowing either target
again fails here. Collecting ``backend/tests`` directly would always see the full tree and
could never catch that.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE_TARGETS = ("coverage-gate", "check-all")
_FULL_TREE = "backend/tests"

# Options whose next token is a value, not a test path.
_OPTIONS_WITH_VALUE = {"-m", "-k", "-p", "-c", "-o", "--cov", "--cov-config", "--cov-report"}

# Top-level test directories a gate run must reach.
_REQUIRED_DIRS = ("core", "services", "routers", "mcp", "steps", "filters", "integrations")

# Collected items, parametrized cases included. Measured 2026-10-21: core plus services alone
# collect 1,598 items and the full tree collects 3,435, so 2,500 fails a narrowing back to
# core plus services and still leaves room for normal test churn.
_MIN_COLLECTED = 2500


def _dry_run(target: str) -> str:
    result = subprocess.run(
        ["make", "-n", target],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.replace("\\\n", " ")


def _pytest_paths(command_text: str) -> list[list[str]]:
    """Return the positional path arguments of every pytest invocation in *command_text*."""
    invocations: list[list[str]] = []
    for line in command_text.splitlines():
        if "pytest" not in line:
            continue
        tokens = shlex.split(line)
        start = next(i for i, tok in enumerate(tokens) if tok.endswith("pytest")) + 1
        paths: list[str] = []
        skip_next = False
        for tok in tokens[start:]:
            if skip_next:
                skip_next = False
                continue
            if tok in _OPTIONS_WITH_VALUE:
                skip_next = True
                continue
            if tok.startswith("-"):
                continue
            paths.append(tok)
        invocations.append(paths)
    return invocations


@pytest.mark.parametrize("target", _GATE_TARGETS)
def test_gate_target_runs_the_full_backend_tree(target: str) -> None:
    invocations = _pytest_paths(_dry_run(target))

    assert invocations, f"make -n {target} printed no pytest invocation"
    for paths in invocations:
        assert paths == [_FULL_TREE], (
            f"make {target} runs pytest on {paths}; it must run {_FULL_TREE!r} so no "
            "test directory silently drops out of the gate"
        )


def test_gate_population_spans_the_tree_and_clears_the_floor() -> None:
    paths = _pytest_paths(_dry_run("coverage-gate"))[0]

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *paths],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    node_ids = [line for line in result.stdout.splitlines() if "::" in line]

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert len(node_ids) >= _MIN_COLLECTED, f"only {len(node_ids)} tests collected"
    # Node ids are relative to pytest's rootdir (backend/), e.g. "tests/routers/test_x.py::t".
    reached = {
        node.removeprefix("backend/").split("/")[1]
        for node in node_ids
        if node.removeprefix("backend/").startswith("tests/")
    }
    missing = [d for d in _REQUIRED_DIRS if d not in reached]
    assert not missing, f"gate collection never reaches backend/tests/{missing}"
