"""Non-vacuity canary for backend/pyproject.toml ruff rules."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = _REPO_ROOT / "backend"
_PYPROJECT = _BACKEND_DIR / "pyproject.toml"
_CANARY = _BACKEND_DIR / "tests" / "fixtures" / "lint_canary" / "canary_violations.py"

_EXPECTED_CODES = frozenset(
    {
        "ASYNC230",
        "ASYNC240",
        "BLE001",
        "DTZ001",
        "ERA001",
        "G004",
        "G201",
        "I002",
        "PGH003",
        "S608",
        "TID251",
        "TID252",
    }
)


def _ruff_codes(
    config_path: Path, stdin_filename: str = "backend/services/_lint_canary.py"
) -> set[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(config_path),
            "--output-format=json",
            "--stdin-filename",
            stdin_filename,
            "-",
        ],
        input=_CANARY.read_text(encoding="utf-8"),
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), result.stderr
    findings = json.loads(result.stdout)
    return {item["code"] for item in findings}


def test_pyproject_enforces_all_guardrail_rules() -> None:
    reported = _ruff_codes(_PYPROJECT)
    missing = _EXPECTED_CODES - reported
    assert not missing, (
        f"backend/pyproject.toml did not report expected ruff codes: {sorted(missing)}"
    )


def test_init_reexports_are_exempt_from_tid252() -> None:
    reported = _ruff_codes(_PYPROJECT, stdin_filename="backend/services/__init__.py")
    assert "TID252" not in reported


def test_canary_detects_removed_rule(tmp_path: Path) -> None:
    stripped = _PYPROJECT.read_text(encoding="utf-8").replace('    "DTZ",', "")
    tmp_config = tmp_path / "pyproject.toml"
    tmp_config.write_text(stripped, encoding="utf-8")

    reported = _ruff_codes(tmp_config)
    assert "DTZ001" not in reported


def test_canary_fixture_is_excluded_from_normal_lint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format=json", "backend"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
