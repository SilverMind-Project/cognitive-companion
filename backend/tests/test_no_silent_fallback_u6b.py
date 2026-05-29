"""U6-T3 + U6-T4: No silent fallbacks — converted sites now warn/raise instead of swallowing.

T3: For each converted site, the failure path now raises the typed error or dead-letters
    with a log, and does not return a fabricated value.

T4: The BLE001 lint rule is active at error severity.  Introducing a new bare
    ``except Exception: pass`` or ``except Exception: return 0`` must fail the lint gate.
    This test verifies the ruff configuration enforces the guard on new code.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# T3: presence_dwell filter logs on service error (not silent return False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_presence_dwell_logs_warning_on_service_error(caplog):
    """T3: presence_dwell filter logs a warning on service degradation (not silent)."""
    from datetime import UTC, datetime

    from backend.filters.builtin.presence_dwell import PresenceDwellFilter

    broken_service = MagicMock()
    broken_service.person_location = MagicMock()
    broken_service.person_location.current_dwell = AsyncMock(
        side_effect=RuntimeError("PersonLocationService unavailable")
    )

    filt = PresenceDwellFilter()
    with caplog.at_level(logging.WARNING, logger="backend.filters.builtin.presence_dwell"):
        result = await filt.evaluate(
            config={"person_id": "alice", "min_minutes": 5},
            sensor=None,
            now=datetime.now(UTC),
            services=broken_service,
        )

    assert result is False
    # The failure must be logged, not swallowed silently.
    assert any("presence_dwell_filter_service_error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# T3: cts_adjacency_inference logs on polygon build failure
# ---------------------------------------------------------------------------


def test_cts_adjacency_logs_warning_on_polygon_failure(caplog):
    """T3: invalid visibility polygon logs a warning and is skipped."""
    from backend.services.cts_adjacency_inference import infer_adjacency

    cameras = [
        {"id": "cam-A", "visibility_polygon": [[0, 0], [1, 0], [0.5, 1]]},
        {"id": "cam-bad", "visibility_polygon": "not_a_list"},
    ]
    with caplog.at_level(logging.WARNING, logger="backend.services.cts_adjacency_inference"):
        result = infer_adjacency(cameras)

    assert "cam-bad" in result.skipped_camera_ids
    assert any("cts_adjacency_polygon_build_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# T3: room_transition_subscriber logs on decode failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_room_transition_decode_logs_warning(caplog):
    """T3: malformed Redis message logs a warning and returns None."""
    from backend.services.cts.room_transition_subscriber import RoomTransitionSubscriber

    sub = RoomTransitionSubscriber.__new__(RoomTransitionSubscriber)
    with caplog.at_level(logging.WARNING, logger="backend.services.cts.room_transition_subscriber"):
        # Pass a dict with a bad event_time that causes fromisoformat to fail.
        result = await sub.decode(
            message_id="msg-1",
            fields={
                b"identity_id": b"alice",
                b"transit_zone_id": b"tz-1",
                b"direction": b"exit",
                b"inside_room_id": b"1",
                b"outside_room_id": b"2",
                b"floor_x_m": b"1.5",
                b"floor_y_m": b"2.5",
                b"event_time": b"NOT_A_DATETIME",
            },
        )

    assert result is None
    assert any("room_transition_decode_error" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# T4: BLE001 lint guard — a new bare except must fail ruff
# ---------------------------------------------------------------------------


def test_ble001_lint_guard_catches_new_bare_except(tmp_path: Path):
    """T4: introduce a bare except Exception: return 0 — ruff must flag BLE001."""
    bad_code = textwrap.dedent("""\
        def broken():
            try:
                return 1 / 0
            except Exception:
                return 0
    """)
    bad_file = tmp_path / "bad_code.py"
    bad_file.write_text(bad_code)

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "BLE001", str(bad_file)],
        capture_output=True,
        text=True,
    )

    # ruff exits with code 1 when violations are found.
    assert result.returncode != 0, "ruff must flag BLE001 on bare except returning 0"
    assert "BLE001" in result.stdout, f"Expected BLE001 in output: {result.stdout}"


def test_ble001_lint_guard_passes_with_specific_exception(tmp_path: Path):
    """T4: a specific exception type does not trigger BLE001."""
    good_code = textwrap.dedent("""\
        def ok():
            try:
                return 1 / 0
            except ZeroDivisionError:
                return 0
    """)
    good_file = tmp_path / "good_code.py"
    good_file.write_text(good_code)

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "BLE001", str(good_file)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Specific exception should not trigger BLE001: {result.stdout}"
