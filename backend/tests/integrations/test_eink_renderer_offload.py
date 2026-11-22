"""EInkRenderer keeps its blocking MinIO, database, and PIL work off the event loop."""

from __future__ import annotations

import threading
from unittest.mock import Mock

from backend.integrations.eink_renderer import EInkRenderer


def _renderer() -> EInkRenderer:
    return EInkRenderer(db_session_factory=Mock(), minio_client=Mock())


async def test_render_runs_blocking_work_on_a_worker_thread(monkeypatch) -> None:
    loop_thread = threading.get_ident()
    seen: dict[str, object] = {}

    def fake_render_blocking(self, text, template, *rest):
        seen["thread"] = threading.get_ident()
        seen["args"] = (text, template, *rest)
        return ["eink-1"]

    monkeypatch.setattr(EInkRenderer, "_render_blocking", fake_render_blocking)

    result = await _renderer().render("Tea at four", template="info_card", expires_in_minutes=5)

    assert result == ["eink-1"]
    assert seen["thread"] != loop_thread
    assert seen["args"] == ("Tea at four", "info_card", None, None, 5, None, None)


async def test_reset_runs_blocking_work_on_a_worker_thread(monkeypatch) -> None:
    loop_thread = threading.get_ident()
    seen: dict[str, object] = {}

    def fake_reset_blocking(self, sensor_ids):
        seen["thread"] = threading.get_ident()
        return list(sensor_ids or [])

    monkeypatch.setattr(EInkRenderer, "_reset_blocking", fake_reset_blocking)

    assert await _renderer().reset(["eink-1"]) == ["eink-1"]
    assert seen["thread"] != loop_thread
