"""scripts/ccwin: argument validation, exit-code contract, and the live-test guard.

The Windows PC is replaced by fake ``ssh``, ``scp``, and ``curl`` executables on
``PATH``, so these run offline: they pin what ccwin sends and how it maps failures,
not the PC's behaviour (that is exercised by running ccwin against the PC).
"""

from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "scripts" / "ccwin"

_FAKE_SSH = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
if [[ ! -t 0 ]]; then cat >> "$FAKE_STDIN"; fi
case "${FAKE_SSH_MODE:-ok}" in
  ok) echo "remote ok"; exit 0 ;;
  unreachable) echo "ssh: connect to host 192.0.2.30 port 22: Connection timed out" >&2; exit 255 ;;
  remote255) echo "remote tool failed" >&2; exit 255 ;;
  *) exit "$FAKE_SSH_MODE" ;;
esac
"""

_FAKE_SCP = """#!/usr/bin/env bash
printf 'scp %s\\n' "$*" >> "$FAKE_LOG"
exit 0
"""

# Answers GET /guided-sessions?status=<s> with FAKE_LIVE_<s> (default 0) sessions,
# and records every request line (never the key, which arrives on stdin).
_FAKE_CURL = """#!/usr/bin/env bash
config="$(cat)"
[[ "$config" == *'x-api-key: '* ]] || { echo "no key on stdin" >&2; exit 2; }
printf 'curl %s\\n' "$*" >> "$FAKE_LOG"
for arg in "$@"; do
  if [[ "$arg" == *"/guided-sessions?status="* ]]; then
    status="${arg##*status=}"; status="${status%%&*}"
    var="FAKE_LIVE_${status}"
    echo "{\\"items\\": [], \\"total\\": ${!var:-0}}"
    exit 0
  fi
done
echo '{}'
"""


def _executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _git(repo: Path, *args: str) -> None:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "-C", str(repo), *identity, *args], check=True)


@pytest.fixture
def harness(tmp_path: Path):
    """A throwaway repository holding a copy of ccwin, and fakes first on PATH."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "frontend").mkdir()
    shutil.copy2(_SCRIPT, repo / "scripts" / "ccwin")
    (repo / "frontend" / ".nvmrc").write_text("24.16.0\n")
    (repo / ".gitignore").write_text(".env\n")
    _git(repo, "init", "-q")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "files")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "ssh", _FAKE_SSH)
    _executable(bin_dir / "scp", _FAKE_SCP)
    _executable(bin_dir / "curl", _FAKE_CURL)
    log = tmp_path / "calls.log"
    stdin_log = tmp_path / "stdin.log"
    log.touch()
    stdin_log.touch()

    def run(*args: str, **env: str) -> subprocess.CompletedProcess[str]:
        full_env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "FAKE_LOG": str(log),
            "FAKE_STDIN": str(stdin_log),
            **env,
        }
        return subprocess.run(
            ["bash", str(repo / "scripts" / "ccwin"), *args],
            capture_output=True,
            text=True,
            env=full_env,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=60,
        )

    run.repo = repo  # type: ignore[attr-defined]
    run.log = log  # type: ignore[attr-defined]
    run.stdin_log = stdin_log  # type: ignore[attr-defined]
    return run


def test_no_command_prints_usage_and_exits_64(harness):
    result = harness()

    assert result.returncode == 64
    assert "Usage: scripts/ccwin" in result.stderr


def test_an_unknown_command_exits_64(harness):
    assert harness("deploy").returncode == 64


def test_an_unreachable_pc_exits_75_without_retrying(harness):
    result = harness("status", FAKE_SSH_MODE="unreachable")

    assert result.returncode == 75
    assert "unreachable" in result.stderr
    assert len(harness.log.read_text().splitlines()) == 1


def test_a_remote_failure_with_ssh_code_255_is_not_mistaken_for_unreachable(harness):
    assert harness("status", FAKE_SSH_MODE="remote255").returncode == 255


@pytest.mark.parametrize(("remote_code", "meaning"), [(73, "in use"), (74, "lock held")])
def test_the_pcs_refusals_pass_through_unchanged(harness, remote_code, meaning):
    assert harness("status", FAKE_SSH_MODE=str(remote_code)).returncode == remote_code, meaning


def test_remote_commands_run_the_deployed_harness_with_exact_exit_codes(harness):
    harness("status")

    line = harness.log.read_text().splitlines()[0]
    assert "-File C:\\ccwin\\bin\\ccwin-remote.ps1 status" in line
    assert line.rstrip().endswith("exit $LASTEXITCODE")


def test_gradle_rejects_a_task_that_could_inject_into_the_remote_shell(harness):
    result = harness("gradle", ":app:assembleDebug;", "calc")

    assert result.returncode == 64
    assert harness.log.read_text() == ""


def test_adb_arguments_travel_as_one_encoded_value(harness):
    harness("adb", "-s", "emulator-5584", "shell", "getprop", "ro.build.version.sdk")

    line = harness.log.read_text().splitlines()[0]
    encoded = line.split("-ArgsBase64' ")[1].split()[0].strip("'")
    decoded = base64.b64decode(encoded).decode().rstrip("\0").split("\0")
    assert decoded == ["-s", "emulator-5584", "shell", "getprop", "ro.build.version.sdk"]


def test_adb_refuses_double_quotes(harness):
    assert harness("adb", "shell", 'echo "x"').returncode == 64


def test_sync_requires_an_https_companion_url(harness):
    result = harness("sync", CC_COMPANION_URL="http://192.0.2.10:8081/companion")

    assert result.returncode == 64
    assert "https://" in result.stderr


def test_sync_refuses_uncommitted_work_unless_asked_to_snapshot_it(harness):
    (harness.repo / "frontend" / "new.txt").write_text("not committed\n")

    result = harness("sync", CC_COMPANION_URL="https://companion.example/companion")

    assert result.returncode == 64
    assert "--allow-dirty" in result.stderr


def _write_dotenv(repo: Path) -> None:
    (repo / ".env").write_text(
        "CC_CAREGIVER_API_KEY=caregiver-secret\nCC_COMPANION_TEST_API_KEY=device-secret\n"
    )


def test_live_tests_refuse_while_a_guided_routine_is_live(harness):
    _write_dotenv(harness.repo)

    result = harness("test-instrumented", "tablet", FAKE_LIVE_summoning="1")

    assert result.returncode == 69
    assert "1 summoning" in result.stderr
    calls = harness.log.read_text()
    assert "/guided-sessions?status=summoning" in calls
    # Nothing reached the PC, and the test surface was not even registered.
    assert "ccwin-remote.ps1" not in calls
    assert "/companion-surfaces" not in calls


def test_live_tests_register_the_surface_and_send_the_key_only_on_stdin(harness):
    _write_dotenv(harness.repo)

    result = harness("test-instrumented", "tv")

    assert result.returncode == 0, result.stderr
    calls = harness.log.read_text()
    for status in ("summoning", "active", "waiting", "escalated", "caregiver_takeover"):
        assert f"/guided-sessions?status={status}" in calls
    assert "/companion-surfaces" in calls
    remote_line = next(line for line in calls.splitlines() if "ccwin-remote.ps1" in line)
    assert "test-instrumented" in remote_line
    assert "'-Avd' 'tv'" in remote_line
    # Neither key is ever on a command line; the device key reaches the PC on stdin,
    # and the caregiver key never leaves this box.
    assert "device-secret" not in calls
    assert "caregiver-secret" not in calls
    sent = harness.stdin_log.read_text()
    assert "ccApiKey=device-secret" in sent
    assert "ccSurfaceId=ccwin-test-device" in sent
    assert "caregiver-secret" not in sent


def test_live_tests_need_the_device_key(harness):
    (harness.repo / ".env").write_text("CC_CAREGIVER_API_KEY=caregiver-secret\n")

    result = harness("test-instrumented", "tablet")

    assert result.returncode == 64
    assert "CC_COMPANION_TEST_API_KEY" in result.stderr
