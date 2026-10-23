"""scripts/check_doc_refs.py must flag a dead file reference and pass a tree without one."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_doc_refs.py"


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_dead_reference_fails(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "real.py").write_text("")
    (tmp_path / "CLAUDE.md").write_text("See `backend/real.py` and `backend/gone.py`.\n")

    result = _run(tmp_path)

    assert result.returncode == 1
    assert "CLAUDE.md:1: backend/gone.py" in result.stdout
    assert "real.py" not in result.stdout


def test_a_tree_without_dead_references_passes(tmp_path: Path) -> None:
    skill = tmp_path / ".claude" / "skills" / "x"
    skill.mkdir(parents=True)
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "app.ts").write_text("")
    (skill / "SKILL.md").write_text(
        "Uses `@/app.ts`, a placeholder `NNNN_name.py`, and a bare `.py` extension.\n"
        "```\nnot/checked/in/a/code/block.py\n```\n"
    )

    assert _run(tmp_path).returncode == 0


def test_this_repository_has_no_dead_references() -> None:
    result = _run(_SCRIPT.parents[1])

    assert result.returncode == 0, result.stdout
